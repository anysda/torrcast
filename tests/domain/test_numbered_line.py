"""Зеркало :mod:`torrcast.domain.numbered_line`: линейка франшизы и всё, что вне её."""

from torrcast.domain.compose import _compose
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def test_the_numbered_parts_make_the_line_and_the_rest_waits_behind() -> None:
    """Номер в меню значит номер части, поэтому линейка и хвост считаются отдельно."""
    line, tail = _numbered_line(
        [
            Picture(title="Брат 2", year=2000, part=2),
            Picture(title="Брат", year=1997),
            Picture(title="Другое кино", year=2010, kind="other"),
        ]
    )

    assert [p.title for p in line] == ["Брат", "Брат 2"]
    assert [p.title for p in tail] == ["Другое кино"]


def test_a_line_without_a_single_number_is_the_whole_pool() -> None:
    """Нумерации нет - значит, и линейки нет: под номерами идёт всё, что нашлось."""
    line, tail = _numbered_line(
        [Picture(title="Брат", year=1997), Picture(title="Сестра", year=2019)]
    )

    assert [p.title for p in line] == ["Брат", "Сестра"]
    assert tail == []


def test_the_parts_of_the_line_stand_in_the_order_of_their_numbers() -> None:
    line, _tail = _numbered_line(
        [Picture(title="Третья", year=2010, part=3), Picture(title="Вторая", year=2000, part=2)]
    )

    assert [p.title for p in line] == ["Вторая", "Третья"]


def _composed(year: int, *names: tuple[int, str]) -> Picture:
    """Картина, собранная из настоящей горсти имён: номер части она считает сама."""
    group = [Release(raw_name=title, title=title) for count, title in names for _ in range(count)]
    return _compose("movie", year, group)


def test_the_numbered_spine_of_the_franchise_decides_which_namesake_heads_the_line() -> None:
    """🔴 TC-859. «Трансформеры» 2007 стоят в голове линейки, а не «Трансформеры» 1986.

    Номер части «Трансформерам 3» (2011) дают восемь имён из сорока, и это меньшинство.
    Отбери его - номерных частей не останется вовсе, линейка станет простым списком, и
    голова меню съедет на «Трансформеров» (1986), которых не спрашивали. Поэтому номер
    тут считает сама сборка (:func:`~torrcast.domain.compose._compose`), а не рука.
    """
    line, tail = _numbered_line(
        [
            _composed(1986, (10, "Трансформеры")),
            _composed(2007, (18, "Трансформеры")),
            _composed(
                2011,
                (32, "Трансформеры: Тёмная сторона Луны"),
                (8, "Трансформеры 3: Тёмная сторона Луны"),
            ),
        ]
    )

    assert [(p.year, p.part) for p in line] == [(2007, None), (2011, 3)]
    assert [p.year for p in tail] == [1986]
