"""Показ с закладки, куда копией не войти: лента уходит в сплошной перекод."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.clean_stand import Recoder, stand
from tests.usecases.feed_pack.world import feed, grid, vault
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.stream_pack.grid import Grid

if TYPE_CHECKING:
    from pathlib import Path


def test_a_bookmark_the_copy_cannot_open_is_recoded_whole_from_its_slot(
    tmp_path: Path, journal: Path
) -> None:
    """Вход не IDR - вся лента в перекод с границы слота, без пробного прогона.

    Живой замер (5212 МБ, закладка 177.837): копия со входа 174.758 не дала кадра за
    99 с, вкладка отвечала ``PIPELINE_ERROR_DECODE``; сплошной перекод - кадр за 0.28 с.
    """
    seen: list[str] = []
    commands = stand(False, seen)
    coder = Recoder()
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
    """IDR на входе или сверка молчит и после пробного захода - показ идёт копией."""
    for clean, asked in (
        (True, ["вход 177.837", "проба"]),
        (None, ["вход 177.837", "проба", "вход 177.837"]),
    ):
        seen: list[str] = []
        stand(clean, seen)
        coder = Recoder()
        show = feed(tmp_path / str(clean), grid=grid(600.0, 10.0), recoder=coder)

        show.begin(177.837)

        assert seen == asked
        assert show.encode is None and not coder.stopped
        assert show.recoder is not None


def test_without_a_recoder_nothing_is_asked(tmp_path: Path, journal: Path) -> None:
    """Без кодировщика перекодировать нечем: сверка входа стоила бы ffmpeg впустую."""
    seen: list[str] = []
    stand(False, seen)
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
    stand(False, seen)
    coder = Recoder()
    keys = Grid.on_keyframes([float(at) for at in range(0, 600, 10)], 600.0)
    assert keys.on_keys
    show = feed(tmp_path, grid=keys, recoder=coder)

    show.begin(177.837)

    assert not [said for said in seen if said.startswith("вход")]
    assert show.encode is None and not coder.stopped
    assert show.recoder is not None


def test_an_entry_unknown_on_a_cold_swarm_is_asked_again_after_the_pilot(
    tmp_path: Path, journal: Path
) -> None:
    """Сверка молчит на холодном рое - спросить снова, когда пробный заход притянул место.

    Живой замер (TS холодный, закладка 5000): сверка не ответила за потолок, копия вошла с
    4990.694 без IDR, вкладка не дала ни кадра; в кэше сверок то же место - ``False``.
    """
    seen: list[str] = []
    commands = stand((None, False), seen)
    coder = Recoder()
    show = feed(tmp_path, grid=grid(600.0, 10.0), recoder=coder)

    assert show.begin(177.837) == 177.837

    assert seen == ["вход 177.837", "проба", "вход 177.837"]
    assert show.recoder is None and coder.stopped and show.vault is None
    command = commands[0]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-ss") + 1] == "170.000"
