"""Заход упаковки: кого предупредить, где измерить старт и что сказать зрителю."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import torrcast.usecases.feed_pack._state as _state
from tests.usecases.feed_pack.world import clock, feed, grid, packer, signals
from torrcast.domain.hls_settings import PACK_DIR
from torrcast.usecases.feed_pack.feed_restart import _restart

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@dataclass
class _Recoder:
    """Кодировщик тяжёлых кусков: запоминает, когда ему сказали о новом месте показа."""

    spare: Any = None
    seen: list[str] = field(default_factory=list)

    def opening(self, slot: int) -> None:
        self.seen.append(f"голова {slot}")

    def note(self, slot: int, how: str) -> None: ...

    def holding(self, slot: int, size: int) -> bool:
        return False


def _tract(
    monkeypatch: pytest.MonkeyPatch, seen: list[str], at: float = 0.0
) -> list[tuple[Any, ...]]:
    """Подставить заходу поддельный медиатракт; возвращает поднятые прогоны."""
    started: list[tuple[Any, ...]] = []

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        started.append((command, out, run, first, kwargs))
        run.mkdir(parents=True, exist_ok=True)
        return packer(out.parent, out=out, run=run, first=first)

    def _pilot(source: str, want: float) -> float:
        seen.append("проба")
        return at

    monkeypatch.setattr(_state, "pack_start", _pilot, raising=False)
    monkeypatch.setattr(
        _state, "ffmpeg_pack_command", lambda *a, **k: ["ffmpeg", *map(str, a[4:6])]
    )
    monkeypatch.setattr(_state, "Packer", type("Fake", (), {"start": staticmethod(_start)}))
    return started


def test_the_encoder_learns_about_the_new_place_before_the_pilot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: Path
) -> None:
    """Голову прогона кодировщик обязан начать не позже упаковщика: пробный стоит 0.5-1.7 с."""
    clock(monkeypatch)
    seen: list[str] = []
    started = _tract(monkeypatch, seen)
    recoder = _Recoder(spare=tmp_path / "recode")
    show = feed(tmp_path, recoder=recoder)

    _restart(show, 5, lambda slot, size: False)

    assert recoder.seen == ["голова 5"]
    assert seen == ["проба"], "пробный прогон обогнал кодировщика"
    assert started and started[0][3] == 5


def test_a_whole_film_recode_never_asks_the_pilot_and_stands_where_the_grid_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: Path
) -> None:
    """Перекодирующему прогону пробный вреден: по ``-ss`` он встаёт точно, докатки нет.

    Измеренное ``at`` увело бы весь прогон на сегмент назад - эта грабля уже стоила
    отладки кодировщику.
    """
    clock(monkeypatch)
    seen: list[str] = []
    started = _tract(monkeypatch, seen, at=8.0)
    show = feed(tmp_path, grid=grid(60.0, 10.0), encode=object())

    _restart(show, 3, lambda slot, size: False)

    assert seen == [], "пробный прогон при сплошном перекоде звать нельзя"
    assert started[0][4]["at"] == 30.0


def test_the_run_starts_where_it_was_measured_and_the_rollback_is_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: Path
) -> None:
    """Место захода берут у пробного прогона, а докатку называют зрителю вслух.

    ``-segment_times`` считаются от ``at``, а муксер отмеряет их от первого пакета
    прогона: отдай мы задуманное начало - и все резы уехали бы на всю докатку.
    """
    clock(monkeypatch)
    seen: list[str] = []
    said: list[str] = []
    started = _tract(monkeypatch, seen, at=28.4)
    show = feed(tmp_path, grid=grid(60.0, 10.0), log=said.append)

    _restart(show, 3, lambda slot, size: False)

    assert started[0][4]["at"] == 28.4
    assert started[0][2] == show.out / PACK_DIR
    assert said == ["упаковка с 30.0 с (докатка 1.6 с)"]


def test_a_run_that_stands_where_it_was_asked_says_nothing_about_a_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: Path
) -> None:
    """Докатки нет - и строки о ней нет: допуск сравнения меньше полкадра."""
    clock(monkeypatch)
    said: list[str] = []
    _tract(monkeypatch, [], at=30.0)
    show = feed(tmp_path, grid=grid(60.0, 10.0), log=said.append)

    _restart(show, 3, lambda slot, size: False)

    assert said == ["упаковка с 30.0 с"]


def test_the_previous_run_is_taken_down_but_its_pieces_stay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, journal: Path
) -> None:
    """Под именем ``vN`` и до, и после перезапуска лежит одно и то же место фильма."""
    clock(monkeypatch)
    _tract(monkeypatch, [])
    show = feed(tmp_path, grid=grid(60.0, 10.0))
    old = packer(tmp_path, first=0, out=show.out)
    (show.out / "v0.ts").write_bytes(b"old")
    show.packer = old

    _restart(show, 3, lambda slot, size: False)

    assert old.stopped == "" and signals(old) == ["terminate"]
    assert (show.out / "v0.ts").exists(), "перезапуск выбросил уже упакованное"
    assert show.packer is not old
