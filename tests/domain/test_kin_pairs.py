"""Зеркало :mod:`torrcast.domain.kin_pairs`: кого ведро подаёт правилу межвидовой склейки."""

from torrcast.domain.kin_pairs import _kin_pairs
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify


def _apart(spot: int) -> int:
    """Склейка, в которой ещё ничего не сведено: каждая сторона сама себе кучка."""
    return spot


def test_one_original_gathers_sides_the_catalogue_named_differently() -> None:
    """🎯 TC-1036. «One Piece» 1999 года лежит сериалом «Большой Куш» и фильмом «Ван-Пис»:
    русские имена разные, и по ним пара не встречалась. Оригинал у неё один."""
    sides = [
        Picture(title="Большой Куш", year=1999, kind="tv", original="One Piece"),
        Picture(title="Ван-Пис", year=1999, kind="movie", original="One Piece"),
    ]

    assert _kin_pairs(sides, slugify, _apart, named=True) == [(0, 1)]


def test_the_russian_name_stays_a_key_of_its_own() -> None:
    """У «Байки Мэтра» оригиналы не равны буквально, и сводит стороны русское имя."""
    sides = [
        Picture(
            title="Байки Мэтра", year=2008, kind="movie", original="Cars Toon: Mater's Tall Tales"
        ),
        Picture(title="Байки Мэтра", year=2008, kind="tv", original="Mater's Tall Tales"),
    ]

    assert _kin_pairs(sides, slugify, _apart, named=True) == [(0, 1)]


def test_the_year_stays_in_the_key() -> None:
    """Под оригиналом «One Piece» стоят сериал 1999 года и фильм 2019-го - две картины."""
    sides = [
        Picture(title="Ван-Пис", year=1999, kind="tv", original="One Piece"),
        Picture(title="Ван-Пис: Стампид", year=2019, kind="movie", original="One Piece"),
    ]

    assert _kin_pairs(sides, slugify, _apart, named=True) == []


def test_a_side_without_a_year_waits_for_the_second_pass() -> None:
    """Год такая сторона занимает у соседа, а сосед становится один только после
    первого захода: до него занимать не у кого."""
    sides = [
        Picture(title="Наруто", year=2007, kind="tv", original="Naruto Shippuuden"),
        Picture(title="Naruto- Shippuuden", year=None, kind="movie", original="Naruto Shippuuden"),
    ]

    assert _kin_pairs(sides, slugify, _apart, named=True) == []
    assert _kin_pairs(sides, slugify, _apart, named=True, undated=True) == [(0, 1)]


def test_a_side_whose_own_pile_already_has_a_year_borrows_nothing() -> None:
    """🔴 Года нет не у стороны, а у КАРТИНЫ. Пачка «Steins;Gate Complete Series» лежит в
    сериале 2011 года, а оригиналом ей подписан фильм: заняв год фильма, сериал утащил бы
    фильм к себе в пул."""
    sides = [
        Picture(title="Врата Штейна", year=2011, kind="tv", original="Steins;Gate"),
        Picture(
            title="Steins;Gate Complete Series",
            year=None,
            kind="tv",
            original="Fuka Ryouiki no Deja vu",
        ),
        Picture(
            title="Врата Штейна: Зона выжженных небес",
            year=2013,
            kind="movie",
            original="Fuka Ryouiki no Deja vu",
        ),
    ]
    piles = {0: 0, 1: 0, 2: 2}

    assert _kin_pairs(sides, slugify, piles.__getitem__, named=True, undated=True) == []


def test_a_side_without_a_year_does_not_guess_between_several_piles() -> None:
    """Под оригиналом стоят две несведённые картины: выбирать было бы гаданием."""
    sides = [
        Picture(title="Ван-Пис", year=1999, kind="tv", original="One Piece"),
        Picture(title="Ван-Пис: Стампид", year=2019, kind="movie", original="One Piece"),
        Picture(title="One Piece", year=None, kind="movie", original="One Piece"),
    ]

    assert _kin_pairs(sides, slugify, _apart, named=True, undated=True) == []


def test_sides_without_an_original_meet_by_the_russian_name_and_the_year() -> None:
    """Ведро голых имён: оригинала нет ни у одной стороны, и всё, что есть, - имя и год."""
    sides = [
        Picture(title="Место встречи изменить нельзя", year=1979, kind="movie"),
        Picture(title="Место встречи изменить нельзя", year=1979, kind="tv"),
    ]

    assert _kin_pairs(sides, slugify, _apart, named=False) == [(0, 1)]
    assert _kin_pairs(sides, slugify, _apart, named=True) == []
