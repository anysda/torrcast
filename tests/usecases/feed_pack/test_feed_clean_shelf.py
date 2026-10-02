"""Голова с полки, куда вкладке не войти: показ уходит в сплошной перекод с её слота."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.clean_stand import Recoder, stand
from tests.usecases.feed_pack.world import feed, grid, lay, vault

if TYPE_CHECKING:
    from pathlib import Path


def test_a_shelf_head_the_tab_cannot_enter_is_recoded_from_its_slot(
    tmp_path: Path, journal: Path
) -> None:
    """Голова с полки без чистого входа - перекод с границы слота, а не кусок прогрева.

    Живой замер («Интерстеллар», закладка 5348.469, на полке v534 из копии BD-AVC):
    «Поток потерян» в четырёх продолжениях из четырёх, ни одного кадра.
    """
    seen: list[str] = []
    commands = stand(None, seen, piece=False)
    coder, shelf = Recoder(), vault(tmp_path)
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
        commands = stand(None, seen, piece=piece)
        coder, shelf = Recoder(), vault(tmp_path / str(piece))
        lay(shelf.dir, 17)
        show = feed(tmp_path / str(piece), grid=grid(600.0, 10.0), recoder=coder, vault=shelf)

        show.begin(177.837)

        assert seen == ["кусок v17.ts", "проба"], "за головой - копия с пробным заходом"
        assert show.vault is shelf and show.encode is None and 17 in coder.done
        assert commands[0][commands[0].index("-ss") + 1] == "180.000"
