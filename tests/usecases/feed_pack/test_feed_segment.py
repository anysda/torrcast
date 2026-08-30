"""Ответ на запрос сегмента: готовый файл, прогретое с диска или честное «не будет»."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

import pytest

import torrcast.usecases.feed_pack.feed_segment as feed_segment
from tests.usecases.feed_pack.world import feed, grid, lay, tract, vault
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.feed_pack.feed_segment import _have, _segment, _warm
from torrcast.usecases.warm._warm_count import _spots_left
from torrcast.usecases.warm.segment_start import _Clock

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from torrcast.ports.recode.encoding_key import EncodingKey
    from torrcast.usecases.warm.vault import Vault


def _yes(slot: int) -> bool:
    return True


def _noting(asked: list[int]) -> Callable[[int], bool]:
    """Решение об упаковке, которое только запоминает просьбы и ничего не поднимает."""

    def steer(slot: int) -> bool:
        asked.append(slot)
        return True

    return steer


def _quiet(slot: int) -> None:
    """Стык прогретого, который ничего не решает: предмет проб тут - выдача куска."""
    return None


def _watching(seen: list[int]) -> Callable[[int], None]:
    """Стык прогретого, который только запоминает, о каком месте его спросили."""

    def seam(slot: int) -> None:
        seen.append(slot)

    return seam


def test_a_ready_piece_is_answered_at_once_without_touching_the_packing(tmp_path: Path) -> None:
    """Файл на месте - разбираться с упаковкой незачем: это обычный ход показа."""
    tract()
    asked: list[int] = []
    show = feed(tmp_path)
    lay(show.out, 2)

    answer = _segment(show, 2, _noting(asked), _quiet)

    assert answer == show.out / "v2.ts" and asked == []


def test_a_name_the_manifest_never_promised_goes_nowhere_near_the_packing(tmp_path: Path) -> None:
    """🔴 TC-622. Номер за сеткой не спорит с упаковкой: ждать по манифесту нечего.

    Раньше он шёл в решение как есть, а там сетка зажимала его в границы - и один GET
    давал 61 перезапуск упаковки с конца фильма.
    """
    fake = tract()
    asked: list[int] = []
    show = feed(tmp_path, grid=grid(60.0, 10.0), wait=120.0)

    assert _segment(show, 99999, _noting(asked), _quiet) is None
    assert asked == [] and fake.slept == [], "за сеткой ждали, вместо того чтобы ответить сразу"

    lay(show.out, 99999)
    assert _segment(show, 99999, _yes, _quiet) == show.out / "v99999.ts", (
        "лежащий файл отдаётся всегда"
    )


def test_the_warmed_piece_answers_before_any_argument_with_the_packing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """В этом весь смысл прогрева: перемотка в прогретое отвечает файлом, не поднимая ffmpeg."""
    tract()
    asked: list[int] = []
    seen: list[int] = []
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store)
    monkeypatch.setattr(feed_segment, "segment_start", lambda path: _Clock(30.0, movie=True))
    lay(store.dir, 3)

    answer = _segment(show, 3, _noting(asked), _watching(seen))

    assert answer == store.dir / "v3.ts" and asked == []
    assert seen == [3], (
        "выдача прогретого прошла мимо стыка: за концом прогретого некому поднять упаковку"
    )


def test_a_warmed_piece_over_the_ceiling_is_not_warmed_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Прогретое идёт мимо обоих потолков веса, поэтому тяжёлая копия прогретой не считается.

    Замер («Тачки» 2006, 39% фильма тяжелее потолка): 32 BUFFERING и 20 пинков за
    14 минут, пока показ брал с диска копии по 17-44 МБ.
    """
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store, cap=100)
    monkeypatch.setattr(feed_segment, "segment_start", lambda path: _Clock(30.0, movie=True))
    lay(store.dir, 3, size=101)

    assert _warm(show, 3) is None

    lay(store.dir, 3, size=100)
    assert _warm(show, 3) == store.dir / "v3.ts", "кусок ровно по потолку показу годится"


def test_a_warmed_piece_from_another_place_is_repacked_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Чужой таймкод под верным именем не уходит зрителю и не роняет показ."""
    fake = tract()
    said: list[str] = []
    asked: list[int] = []
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store, wait=1.0, log=said.append)
    foreign = lay(store.dir, 3)
    copied = foreign.read_bytes()
    store.spot(3).touch()
    monkeypatch.setattr(
        feed_segment, "segment_start", lambda path: _Clock(1237.68, movie=True), raising=False
    )

    def pack_live(slot: int) -> bool:
        asked.append(slot)
        lay(show.out, slot)
        return True

    answer = _segment(show, 3, pack_live, _quiet)

    assert answer == show.out / "v3.ts" and asked == [3]
    assert not foreign.exists(), "чужой кусок остался доступен следующему запросу"
    assert not store.spot(3).exists(), "метка перекода пережила забракованный кусок"
    foreign.write_bytes(copied)
    assert _spots_left(cast("Vault", store), (3,), cast("EncodingKey", object())) == (3,), (
        "возвращённая копия не попала в перекод"
    )
    assert said == [phrase("feed.warm_off_grid", slot=3, diff="+1207.68")]
    assert fake.slept == []


def test_a_warmed_piece_whose_start_was_never_measured_is_handed_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-879. Не прочтя начала, показ кусок ОТДАЁТ, а не стирает.

    Вопрос тут другой, чем у сторожа укладки: тот решает, класть ли, и платит за ошибку
    перекладкой того же места, а этот решает, отдавать ли УЖЕ ЛЕЖАЩЕЕ, и платит стёртым
    прогревом. Замена куску одна - живая упаковка того же места, а её начало не сверяет
    никто: отказ менял бы непроверенное на непроверенное, теряя по дороге весь прогрев.

    Стоило это ВСЕГО прогрева на приставке: во фрагменте CMAF времени фильма нет ни в
    одном байте, прежнее «не прочитан - значит мимо сетки» стирало КАЖДЫЙ прогретый кусок,
    и за прогон не выдавалось ни одного ``warm-copy``.
    """
    said: list[str] = []
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store, log=said.append)
    lay(store.dir, 3)

    for clock in (_Clock(math.nan, movie=False), _Clock(math.nan, movie=True)):
        monkeypatch.setattr(feed_segment, "segment_start", lambda path, answer=clock: answer)
        assert _warm(show, 3) == store.dir / "v3.ts", "прогретое стёрто по незнанию"
    assert said == [], "показ назвал промахом то, чего не измерял"


def test_the_last_warmed_piece_whose_end_was_never_measured_is_handed_over_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Тот же разбор на хвосте: не прочтя КОНЦА, показ последний кусок тоже отдаёт.

    Мера хвоста читает пакеты MPEG-TS, во фрагменте CMAF их нет, и на приставке она
    молчала на каждом последнем куске - то есть отказ по ней стирал прогретый хвост
    фильма ровно там, где мерить было нечем.
    """
    said: list[str] = []
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store, log=said.append)
    last = show.grid.count - 1
    lay(store.dir, last)
    monkeypatch.setattr(feed_segment, "segment_start", lambda path: _Clock(math.nan, movie=False))
    monkeypatch.setattr(feed_segment, "segment_end", lambda path: math.nan)

    assert _warm(show, last) == store.dir / f"v{last}.ts", "хвост стёрт по незнанию"
    assert said == []

    monkeypatch.setattr(feed_segment, "segment_end", lambda path: 1.0)
    assert _warm(show, last) is None, "измеренный обрыв хвоста перестал ловиться"


def test_a_hopeless_place_is_answered_the_moment_the_packing_says_so(tmp_path: Path) -> None:
    """«Файла не будет» - ответ сразу: держать поток раздачи после приговора незачем."""
    fake = tract()
    show = feed(tmp_path, wait=120.0)

    assert _segment(show, 1, lambda slot: False, _quiet) is None
    assert fake.slept == [], "после приговора показ всё равно ждал"


def test_a_busy_decision_is_waited_out_by_the_file_and_not_by_the_queue(tmp_path: Path) -> None:
    """Замок занят - сосед ждёт свой файл, а не очередь: решение стоит до минуты."""
    fake = tract()
    asked: list[int] = []
    show = feed(tmp_path, wait=1.0)
    show.lock.acquire()

    assert _segment(show, 1, _noting(asked), _quiet) is None
    assert asked == [] and fake.slept == [0.2] * 5


def test_a_piece_is_ours_whether_it_lies_in_the_window_or_on_the_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запас показа считает и окно, и прогретое: приёмнику всё равно, откуда кусок."""
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store)
    monkeypatch.setattr(
        feed_segment,
        "segment_start",
        lambda path: pytest.fail("предикат запаса прочитал голову прогретого"),
    )
    lay(show.out, 1)
    lay(store.dir, 2)

    assert _have(show, 1) and _have(show, 2) and not _have(show, 3)
