"""Показ с закладки, куда копией не войти: лента уходит в сплошной перекод."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import factory, feed, grid, packer, tract, vault
from torrcast.adapters.recode.encode import Encode

if TYPE_CHECKING:
    from pathlib import Path


class _Pace:
    def table(self) -> list[tuple[str, float]]:
        return [("ultrafast", 1.0), ("veryfast", 2.0)]


@dataclass
class _Recoder:
    """Кодировщик тяжёлых кусков: помнит, чем его просили кодировать и гасили ли."""

    spare: Any = None
    done: set[int] = field(default_factory=set)
    fitted: list[tuple[float, str]] = field(default_factory=list)
    stopped: bool = False
    pace: _Pace = field(default_factory=_Pace)

    def fit(self, span: float, preset: str) -> Encode:
        self.fitted.append((span, preset))
        return Encode(preset=preset, mbit=7.5)

    def stop(self) -> None:
        self.stopped = True

    def opening(self, slot: int) -> None: ...

    def note(self, slot: int, how: str) -> None: ...

    def holding(self, slot: int, size: int = 0) -> bool:
        return False

    def after_recode(self, slot: int) -> bool:
        return False


def _stand(clean: bool | None, seen: list[str]) -> list[list[str]]:
    """Стенд захода: что ответила сверка входа и какие команды упаковки поднялись."""
    commands: list[list[str]] = []

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        commands.append(command)
        run.mkdir(parents=True, exist_ok=True)
        return packer(out.parent, out=out, run=run, first=first)

    def _pilot(source: str, want: float) -> tuple[float, float]:
        seen.append("проба")
        return want, want

    def _clean(source: str, at: float) -> bool | None:
        seen.append(f"вход {at}")
        return clean

    tract(settle_start=_pilot, opens_clean=_clean, packer=factory(_start))
    return commands


def test_a_bookmark_the_copy_cannot_open_is_recoded_whole_from_its_slot(
    tmp_path: Path, journal: Path
) -> None:
    """Вход не IDR - вся лента в перекод с границы слота, без пробного прогона.

    Живой замер (5212 МБ, закладка 177.837): копия со входа 174.758 не дала кадра за
    99 с, вкладка отвечала ``PIPELINE_ERROR_DECODE``; сплошной перекод - кадр за 0.28 с.
    """
    seen: list[str] = []
    commands = _stand(False, seen)
    coder = _Recoder()
    show = feed(tmp_path, grid=grid(600.0, 10.0), recoder=coder, vault=vault(tmp_path))

    start = show.begin(177.837)

    assert seen == ["вход 177.837"], "пробный прогон перекоду не нужен"
    assert start == 177.837
    assert isinstance(show.encode, Encode) and show.encode.preset == "veryfast"
    assert coder.fitted == [(10.0, "veryfast")]
    assert coder.stopped and show.recoder is None
    assert show.vault is None, "в хранилище копии: стык с ними рвётся так же"
    command = commands[0]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-ss") + 1] == "170.000"


def test_a_clean_or_unknown_entry_keeps_the_copy_path(tmp_path: Path, journal: Path) -> None:
    """IDR на входе или сверка не ответила - показ идёт копией через пробный прогон."""
    for clean in (True, None):
        seen: list[str] = []
        _stand(clean, seen)
        coder = _Recoder()
        show = feed(tmp_path / str(clean), grid=grid(600.0, 10.0), recoder=coder)

        show.begin(177.837)

        assert seen == ["вход 177.837", "проба"]
        assert show.encode is None and not coder.stopped
        assert show.recoder is not None


def test_without_a_recoder_nothing_is_asked(tmp_path: Path, journal: Path) -> None:
    """Без кодировщика перекодировать нечем: сверка входа стоила бы ffmpeg впустую."""
    seen: list[str] = []
    _stand(False, seen)
    show = feed(tmp_path, grid=grid(600.0, 10.0))

    show.begin(177.837)

    assert seen == ["проба"]
    assert show.encode is None
