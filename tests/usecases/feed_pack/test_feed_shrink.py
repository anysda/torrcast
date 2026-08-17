"""Тяжёлый кусок на последнем гейте: ужать на месте или честно пропустить место."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import torrcast.usecases.feed_pack._state as _state
import torrcast.usecases.feed_pack.feed_shrink as shrink_module
from tests.usecases.feed_pack.world import clock, feed, grid, lay, packer
from torrcast.usecases.feed_pack.feed_shrink import _shrink, _skip

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@dataclass(frozen=True)
class _Encode:
    mbit: float = 4.0


@dataclass
class _Pace:
    def table(self) -> list[tuple[str, float]]:
        return [("veryfast", 1.0), ("ultrafast", 2.0)]


@dataclass
class _Recoder:
    """Кодировщик тяжёлых кусков под рукой зеркала: перекода нет, есть только ответы."""

    spare: Path
    over_wait: float = 5.0
    fits: bool = False
    size: int = 5
    done: set[int] = field(default_factory=set)
    pace: _Pace = field(default_factory=_Pace)

    def fit(self, span: float, preset: str) -> _Encode:
        return _Encode()

    def ready(self, slot: int) -> Path | None:
        path = self.spare / f"v{slot}.ts"
        return path if self.fits and path.exists() else None


def _tract(monkeypatch: pytest.MonkeyPatch, laid: list[int]) -> None:
    """Подставить ужатию поддельный медиатракт: ffmpeg не поднимается ни разу."""
    monkeypatch.setattr(_state, "ffmpeg_pack_command", lambda *a, **k: ["ffmpeg"])

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        laid.append(first)
        run.mkdir(parents=True, exist_ok=True)
        return packer(run.parent, out=out, run=run, first=first, edge=first)

    monkeypatch.setattr(shrink_module, "Packer", type("Fake", (), {"start": staticmethod(_start)}))


def _recoder(tmp_path: Path, **kwargs: Any) -> _Recoder:
    spare = tmp_path / "recode"
    spare.mkdir(parents=True, exist_ok=True)
    return _Recoder(spare=spare, **kwargs)


def test_a_decision_about_a_place_is_taken_once_and_said_once(tmp_path: Path) -> None:
    """Место уже пропущено - второй раз ни ужимать, ни говорить о нём не надо."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append)
    show.skipped.add(4)

    assert _shrink(show, 4, 20_000_000) is False and said == []


def test_without_an_encoder_the_place_is_honestly_skipped_and_named(
    tmp_path: Path, journal: Path
) -> None:
    """Ужимать нечем - место пропускается вслух: приёмнику про пропуск отвечает показ."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append)

    assert _shrink(show, 4, 20_000_000) is False
    assert show.skipped == {4}
    assert said == [
        "⚠️ v4 пропускаю: кусок тяжелее потолка (20 МБ), а ужимать нечем - "
        "этого места в показе не будет"
    ]


def test_on_a_whole_film_recode_a_side_run_is_forbidden(tmp_path: Path, journal: Path) -> None:
    """Чужой заход в середину сплошного перекода - это смена SPS на ходу, её ТВ не переживёт."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append, recoder=_recoder(tmp_path), encode=object())

    assert _shrink(show, 4, 0) is False
    assert said and "ужать нельзя" in said[0]
    assert " (0 МБ)" not in said[0], "вес не измерен - выдумывать его в строке нельзя"


def test_a_recode_that_arrived_while_we_waited_for_the_lock_is_taken_as_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пока ждали замок, перекод доехал сам - поднимать ради него ещё один ffmpeg незачем."""
    clock(monkeypatch)
    laid: list[int] = []
    _tract(monkeypatch, laid)
    recoder = _recoder(tmp_path, fits=True)
    lay(recoder.spare, 4, size=5)
    show = feed(tmp_path, recoder=recoder, cap=100)

    assert _shrink(show, 4, 20_000_000) is True
    assert laid == [] and show.skipped == set()


def test_a_shrunk_piece_that_fits_the_ceiling_saves_the_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: Path
) -> None:
    """Ужатие - один короткий прогон ровно на этот сегмент; влез - место спасено."""
    clock(monkeypatch)
    laid: list[int] = []
    said: list[str] = []
    _tract(monkeypatch, laid)
    recoder = _recoder(tmp_path)
    show = feed(tmp_path, recoder=recoder, log=said.append, cap=100, grid=grid(60.0, 10.0))

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        laid.append(first)
        run.mkdir(parents=True, exist_ok=True)
        lay(recoder.spare, first, size=50)
        recoder.fits = True
        return packer(run.parent, out=out, run=run, first=first, edge=first)

    monkeypatch.setattr(shrink_module, "Packer", type("Fake", (), {"start": staticmethod(_start)}))

    assert _shrink(show, 4, 20_000_000) is True
    assert laid == [4] and show.skipped == set()
    assert said == ["v4 тяжелее потолка (20 МБ) - ужимаю на месте до 4.0 Мбит/с"]


def test_a_shrink_that_did_not_fit_is_a_skip_and_not_a_second_try(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: Path
) -> None:
    """Ужать не вышло - место пропускается: стоять на нём значит крутить круг вечно."""
    clock(monkeypatch)
    said: list[str] = []
    _tract(monkeypatch, [])
    show = feed(tmp_path, recoder=_recoder(tmp_path), log=said.append, grid=grid(60.0, 10.0))

    assert _shrink(show, 4, 20_000_000) is False
    assert show.skipped == {4}
    assert any("ужать не вышло" in line for line in said)


def test_a_skipped_place_is_taken_off_the_encoders_list_too(tmp_path: Path, journal: Path) -> None:
    """Кодировщику за пропущенное место браться уже незачем: копия там детерминирована."""
    recoder = _recoder(tmp_path)
    show = feed(tmp_path, recoder=recoder)

    assert _skip(show, 7, 0, "ужимать нечем") is False
    assert show.skipped == {7} and recoder.done == {7}
