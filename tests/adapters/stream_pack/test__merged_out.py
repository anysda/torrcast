"""Что уходит наружу от перекодированного места: склейка, копия или перекод как есть."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from torrcast.adapters.stream_pack._merged_out import _merged_out
from torrcast.domain.segment_container import FMP4
from torrcast.domain.track_place import TRACK_PLACE_MAX

#: Место слота на ленте, с которым сверяются дорожки склейки.
_WANT = 70.0


def _lay(where: Path, name: str, size: int = 16) -> Path:
    path = where / name
    path.write_bytes(b"x" * size)
    return path


def _merges(dst_size: int = 20) -> Any:
    """Склейка, которая всегда выходит: стенд не поднимает ffmpeg."""

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"m" * dst_size)
        return True

    return merge


def _on_place(piece: Path) -> tuple[float, float]:
    """Обе дорожки склейки стоят на месте слота: стенд это знает, а не меряет ffprobe."""
    return _WANT, _WANT - 0.021


def test_the_recoded_picture_goes_out_with_the_sound_of_the_copy(tmp_path: Path) -> None:
    """Наружу идёт склейка: картинка перекода со звуком копии этого же прогона."""
    seen: list[tuple[str, str]] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((video.name, audio.name))
        dst.write_bytes(b"m" * 20)
        return True

    copy, recode = _lay(tmp_path, "v7.ts", 100), _lay(tmp_path, "spare7.ts", 200)

    source, how = _merged_out(
        tmp_path, 7, copy, recode, 100, 1 << 20, _WANT, merge=merge, starts_of=_on_place
    )

    assert seen == [("spare7.ts", "v7.ts")], "звук взят не у копии"
    assert (source.name, how) == ("mix7.ts", "склейка")


def test_a_merge_that_did_not_happen_sends_the_copy_of_its_own_run_while_it_fits(
    tmp_path: Path,
) -> None:
    """Склейки нет: перекод принёс бы свой звук, поэтому копия своего прогона меньшее зло.

    Про место копии тут ничего не измерено - измерять было нечего, файла склейки нет, - и
    прежний размен остаётся прежним.
    """
    copy, recode = _lay(tmp_path, "v1.ts", 100), _lay(tmp_path, "spare1.ts", 200)

    source, how = _merged_out(
        tmp_path,
        1,
        copy,
        recode,
        100,
        4096,
        _WANT,
        merge=lambda *a, **k: False,
        starts_of=_on_place,
    )

    assert (source, how) == (copy, "копия")


def test_a_copy_over_the_ceiling_loses_even_to_a_broken_seam(tmp_path: Path) -> None:
    """Склейки нет, а копия тяжелее потолка приёмника - наружу идёт перекод со своим швом."""
    copy, recode = _lay(tmp_path, "v1.ts", 5000), _lay(tmp_path, "spare1.ts", 200)

    source, how = _merged_out(
        tmp_path,
        1,
        copy,
        recode,
        5000,
        4096,
        _WANT,
        merge=lambda *a, **k: False,
        starts_of=_on_place,
    )

    assert (source, how) == (recode, "перекод")


def test_a_merge_whose_sound_is_from_another_place_never_reaches_the_viewer(
    tmp_path: Path,
) -> None:
    """🔴 TC-833. Склейка с чужим звуком не выходит наружу, и копия за неё не отвечает.

    Копия тут негодна ровно потому, что звук ПРИШЁЛ ИЗ НЕЁ: разошлись дорожки, значит и её
    собственная картинка стоит на том же чужом месте. Наружу идёт перекод - он собран одним
    заходом, поэтому его картинка и его звук заведомо с одного места.
    """
    copy, recode = _lay(tmp_path, "v0.ts", 100), _lay(tmp_path, "spare0.ts", 200)

    source, how = _merged_out(
        tmp_path,
        0,
        copy,
        recode,
        100,
        1 << 20,
        _WANT,
        merge=_merges(),
        starts_of=lambda piece: (_WANT, _WANT + 123.4),
    )

    assert (source, how) == (recode, "перекод"), "склейка с чужим звуком уехала зрителю"
    assert not (tmp_path / "mix0.ts").exists(), "склейка с чужим звуком осталась лежать"


def test_a_picture_from_another_place_sends_the_copy_and_not_the_recode(
    tmp_path: Path,
) -> None:
    """🔴 Уехать вправе и КОДИРОВЩИК, и тогда годная половина пары - копия, а не перекод.

    Поймано корпусом: заход кодировщика на сетке по опорным кадрам потерял рез и уехал ровно
    на слот (+10.417 с) при исправном звуке. Мерялись бы дорожки друг против друга - промах
    выглядел бы виной звука, и наружу ушёл бы как раз испорченный перекод.
    """
    copy, recode = _lay(tmp_path, "v2.ts", 100), _lay(tmp_path, "spare2.ts", 200)

    source, how = _merged_out(
        tmp_path,
        2,
        copy,
        recode,
        100,
        1 << 20,
        _WANT,
        merge=_merges(),
        starts_of=lambda piece: (_WANT + 10.417, _WANT - 0.033),
    )

    assert (source, how) == (copy, "копия"), "наружу ушла уехавшая картинка перекода"
    assert not (tmp_path / "mix2.ts").exists()


def test_a_track_missing_from_the_head_counts_as_not_being_on_its_place(
    tmp_path: Path,
) -> None:
    """Дорожки в голове куска нет - значит на своём месте её нет: это ответ, а не молчание.

    Ровно так выглядит настоящая поломка: на сдвиге в сотни секунд голова состоит из одного
    видео целиком, и второй дорожки в ней не встречается вовсе.
    """
    copy, recode = _lay(tmp_path, "v0.ts", 100), _lay(tmp_path, "spare0.ts", 200)

    source, how = _merged_out(
        tmp_path,
        0,
        copy,
        recode,
        100,
        1 << 20,
        _WANT,
        merge=_merges(),
        starts_of=lambda piece: (_WANT, math.nan),
    )

    assert (source, how) == (recode, "перекод")


def test_a_merge_nobody_could_check_is_not_taken_on_trust(tmp_path: Path) -> None:
    """Проба молчит про обе дорожки - склейка не уезжает: это не «сойдёт», а «не знаю».

    Цена отказа - шов звука на голове захода кодировщика; цена доверия молчанию - десять
    секунд чужого звука, ради которых карточка и написана.
    """
    copy, recode = _lay(tmp_path, "v0.ts", 100), _lay(tmp_path, "spare0.ts", 200)

    source, how = _merged_out(
        tmp_path,
        0,
        copy,
        recode,
        100,
        1 << 20,
        _WANT,
        merge=_merges(),
        starts_of=lambda piece: (math.nan, math.nan),
    )

    assert (source, how) == (copy, "копия"), "несверенная склейка уехала зрителю"
    assert not (tmp_path / "mix0.ts").exists()


def test_without_a_grid_the_place_is_not_checked_at_all(tmp_path: Path) -> None:
    """Сетки у прогона нет - сверять не с чем, и прежний выбор остаётся прежним.

    Так ходят щупы и стенды; на всех трёх живых путях упаковки сетка есть всегда.
    """
    copy, recode = _lay(tmp_path, "v0.ts", 100), _lay(tmp_path, "spare0.ts", 200)

    source, how = _merged_out(
        tmp_path,
        0,
        copy,
        recode,
        100,
        1 << 20,
        math.nan,
        merge=_merges(),
        starts_of=lambda piece: (123.4, 456.7),
    )

    assert how == "склейка" and source.name == "mix0.ts"


def test_a_sound_within_the_threshold_still_goes_out_as_a_merge(tmp_path: Path) -> None:
    """Отрицательная проба порога: здоровый разброс дорожек склейку не отменяет.

    Первый пакет звука законно встаёт РАНЬШЕ границы слота - на набивку кодировщика AAC, а
    на ровной сетке ещё и потому, что рез идёт по времени. Корпус из 53 здоровых склеек дал
    до 0.1867 с; порог обязан их пропускать, иначе шов вернётся на каждый кусок разом.
    """
    copy, recode = _lay(tmp_path, "v0.ts", 100), _lay(tmp_path, "spare0.ts", 200)

    source, how = _merged_out(
        tmp_path,
        0,
        copy,
        recode,
        100,
        1 << 20,
        _WANT,
        merge=_merges(),
        starts_of=lambda piece: (_WANT, _WANT - TRACK_PLACE_MAX + 0.001),
    )

    assert how == "склейка", "здоровый разброс дорожек отменил склейку"
    assert source.name == "mix0.ts"


def test_the_merge_is_named_and_muxed_by_the_container_of_the_show(tmp_path: Path) -> None:
    """Имя склейки и её муксер - оба из контейнера показа, а не из умолчания завода."""
    seen: list[tuple[str, object]] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((dst.name, kwargs.get("container")))
        dst.write_bytes(b"m" * 20)
        return True

    copy, recode = _lay(tmp_path, "v4.m4s", 100), _lay(tmp_path, "spare4.m4s", 200)

    source, _how = _merged_out(
        tmp_path, 4, copy, recode, 100, 1 << 20, _WANT, FMP4, merge=merge, starts_of=_on_place
    )

    assert seen == [("mix4.m4s", FMP4)]
    assert source.name == "mix4.m4s"
