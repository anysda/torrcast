"""Зеркало :mod:`torrcast.domain.nearly_named`: имя каталога в одной букве от запроса."""

from torrcast.domain.cluster import cluster
from torrcast.domain.nearly_named import nearly_named
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.picture import Picture

_POOL = [
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2008) BDRip 1080p",
    "Тачки / Cars (2006) BDRip 1080p",
]


def _pictures() -> list[Picture]:
    return cluster([parse_release_name(name) for name in _POOL])


def test_one_missing_letter_still_names_the_picture() -> None:
    """🔴 TC-777. «Байки Мэтр» - это «Байки Мэтра», а не отсутствие картины."""
    assert nearly_named("Байки Мэтр", _pictures()) == "байки-мэтра"
    assert nearly_named("Байки Мэтры", _pictures()) == "байки-мэтра"


def test_the_exact_name_is_not_its_own_near_miss() -> None:
    assert nearly_named("Байки Мэтра", _pictures()) == ""


def test_a_letter_inside_the_name_is_another_picture() -> None:
    """🔴 «Кольца власти» и «Кольцо власти» - разное кино, а не описка."""
    rings = cluster([parse_release_name("Кольцо власти: Мировое супергосударство (2007) WEB-DL")])

    assert nearly_named("кольца власти", rings) == ""


_MAD = [
    "Безумный Макс / Mad Max (1979) UHD BDRip 2160p",
    "Безумный Макс 2: Воин дороги / Mad Max 2 (1981) BDRip 1080p",
    "Пираты Карибского моря: Проклятие Чёрной жемчужины (2003) BDRip 1080p",
]


def _mad() -> list[Picture]:
    return cluster([parse_release_name(name) for name in _MAD])


def test_a_letter_inside_a_word_is_a_typo_and_is_forgiven() -> None:
    """🔴 TC-869. «безумний» - это промах клавиши, а не форма слова «безумный».

    Первый круг тут НЕПУСТ: картины найдены, «Безумный Макс» среди них, - и отказ на
    таком круге тем и дорог, что зритель уже получил бы осмысленное меню.
    """
    assert nearly_named("безумний макс", _mad()) == "безумный-макс"


def test_a_letter_at_the_end_of_a_word_is_not_forgiven() -> None:
    """🔴 Граница прощения - конец СЛОВА: там стоит падеж, а не промах клавиши.

    «карибскога» от «карибского» отличается последней буквой слова, и прощать её нельзя
    по той же причине, по какой «Кольца власти» не берут «Кольцо власти».
    """
    assert nearly_named("пираты карибскога моря", _mad()) == ""


def test_a_short_name_is_not_forgiven_a_letter() -> None:
    """У имени из пяти букв одна буква разницы - уже другое слово."""
    assert nearly_named("тачка", _pictures()) == ""


def test_an_unknown_name_has_no_near_miss_in_the_catalogue() -> None:
    assert nearly_named("хоббит и гоблины", _pictures()) == ""
