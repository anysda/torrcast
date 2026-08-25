"""Зеркало :mod:`torrcast.domain.menu_order`: в каком порядке картины видит человек."""

from torrcast.domain.menu_order import menu_order
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int, part: int | None = None, collection: bool = False) -> Picture:
    release = Release(raw_name=title, title=title, collection=collection)
    return Picture(title=title, year=year, part=part, releases=[release])


def test_the_franchise_is_shown_from_its_first_part() -> None:
    """Меню читается сверху вниз, и первым пунктом стоит то, с чего смотрят."""
    line = menu_order([_picture("Брат 2", 2000, part=2), _picture("Брат", 1997)])

    assert [p.title for p in line] == ["Брат", "Брат 2"]


def test_a_collection_stands_aside_while_single_pictures_are_there() -> None:
    """Сборник - это не пункт меню: под номером человек ждёт одну картину."""
    line = menu_order([_picture("Брат дилогия", 2005, collection=True), _picture("Брат", 1997)])

    assert [p.title for p in line] == ["Брат"]


def test_a_menu_of_collections_alone_is_still_a_menu() -> None:
    """Кроме сборников ничего не нашлось - показываем их, а не пустоту."""
    line = menu_order([_picture("Брат дилогия", 2005, collection=True)])

    assert [p.title for p in line] == ["Брат дилогия"]
