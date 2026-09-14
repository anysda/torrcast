"""Сторожа живого поиска на главной странице.

Гейт и CI исполняют Python, а JavaScript-рантайма там нет. Поэтому эти проверки держат
не случайные слова, а договор между сборкой выдачи и плиткой: конечный опрос, его
оба шага, неактивная погасшая находка и личность плитки под фокусом.
"""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
HOME = (STATIC / "home.js").read_text(encoding="utf-8")
TILE = (STATIC / "tile.js").read_text(encoding="utf-8")


def _search() -> str:
    began = HOME.split("  async _runSearch(text) {", 1)[1]
    return began.split("\n  // Выдача пересобирается", 1)[0]


def test_progressive_search_stops_after_sixteen_seconds() -> None:
    """Круг не завершился - телевизор не держит мост бесконечным опросом."""
    search = _search()

    assert "const until = Date.now() + 16000;" in search
    assert "while (Date.now() < until)" in search
    assert "while (true)" not in search


def test_progressive_search_polls_fast_before_its_first_tile() -> None:
    """До первой плитки шаг 150 мс, после неё 400 мс."""
    assert "setTimeout(done, known.length ? 400 : 150)" in _search()


def test_a_dim_search_tile_has_no_activation_handler() -> None:
    """У погасшей картины нет раздач, поэтому клик не открывает пустую карточку."""
    assert "onActivate: hit.dim ? null : TCHome._openCard," in HOME
    assert "if (shape.onActivate)" in TILE


def test_search_focus_follows_the_same_picture_after_a_reorder() -> None:
    """Полная выдача меняет порядок, но пульт остаётся на той же картине."""
    assert "tile.dataset.tcFocusId = shape.focusId;" in TILE
    assert "const ids = TCHome._hitIds(results);" in HOME
    assert "focusId: ids[index]," in HOME
    assert "here.dataset.tcFocusId" in HOME
    assert "tile.dataset.tcFocusId === stood" in HOME
    assert "if (same) same.focus();" in HOME
    assert "tiles[at].focus()" not in HOME
