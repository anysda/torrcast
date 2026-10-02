"""Показ с закладки, куда копией не войти: лента уходит в сплошной перекод."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import factory, feed, grid, lay, packer, tract, vault
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.stream_pack.grid import Grid

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


def _stand(clean: bool | None, seen: list[str], piece: bool | None = True) -> list[list[str]]:
    """Стенд захода: что ответили сверки входа и куска с полки, какие команды поднялись."""
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

    def _piece(path: Path) -> bool | None:
        seen.append(f"кусок {path.name}")
        return piece

    tract(settle_start=_pilot, opens_clean=_clean, piece_opens=_piece, packer=factory(_start))
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


def test_a_grid_laid_on_the_keyframe_map_is_not_asked(tmp_path: Path, journal: Path) -> None:
    """Сетка по принятой карте опорных кадров: вход копией есть у каждого слота.

    Карту с не-IDR входами отвергает её же сторож, так что сверка тут - лишний ffmpeg,
    а её «нет» увело бы в сплошной перекод показ, который играет копией.
    """
    seen: list[str] = []
    _stand(False, seen)
    coder = _Recoder()
    keys = Grid.on_keyframes([float(at) for at in range(0, 600, 10)], 600.0)
    assert keys.on_keys
    show = feed(tmp_path, grid=keys, recoder=coder)

    show.begin(177.837)

    assert not [said for said in seen if said.startswith("вход")]
    assert show.encode is None and not coder.stopped
    assert show.recoder is not None


def test_a_shelf_head_the_tab_cannot_enter_is_recoded_from_its_slot(
    tmp_path: Path, journal: Path
) -> None:
    """Голова с полки без чистого входа - перекод с границы слота, а не кусок прогрева.

    Живой замер («Интерстеллар», закладка 5348.469, на полке v534 из копии BD-AVC):
    «Поток потерян» в четырёх продолжениях из четырёх, ни одного кадра.
    """
    seen: list[str] = []
    commands = _stand(None, seen, piece=False)
    coder, shelf = _Recoder(), vault(tmp_path)
    lay(shelf.dir, 17)
    show = feed(tmp_path, grid=grid(600.0, 10.0), recoder=coder, vault=shelf)

    show.begin(177.837)

    assert seen == ["кусок v17.ts"], "сверка по куску на диске, раздачу не трогают"
    assert show.vault is None and show.recoder is None and coder.stopped
    assert 17 not in coder.done and show.door == 17
    command = commands[0]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-ss") + 1] == "170.000"


def test_a_shelf_head_that_opens_or_is_unknown_is_served_from_the_shelf(
    tmp_path: Path, journal: Path
) -> None:
    """Чистый или несверенный кусок полки - голова с полки, упаковка встаёт за ней копией."""
    for piece in (True, None):
        seen: list[str] = []
        commands = _stand(None, seen, piece=piece)
        coder, shelf = _Recoder(), vault(tmp_path / str(piece))
        lay(shelf.dir, 17)
        show = feed(tmp_path / str(piece), grid=grid(600.0, 10.0), recoder=coder, vault=shelf)

        show.begin(177.837)

        assert seen == ["кусок v17.ts", "проба"], "за головой - копия с пробным заходом"
        assert show.vault is shelf and show.encode is None and 17 in coder.done
        assert commands[0][commands[0].index("-ss") + 1] == "180.000"
