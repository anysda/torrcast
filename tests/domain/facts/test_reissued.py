"""Зеркало :mod:`torrcast.domain.facts.reissued`: год раздачи как год перевыпуска."""

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.reissued import reissued

#: Статья своей картины: год выхода 2001, а раздача расширенной версии несёт 2011.
FELLOWSHIP = Dated(
    "The Lord of the Rings: The Fellowship of the Ring",
    "Q127367",
    frozenset({2001}),
    frozenset({"movie"}),
)
RING = Ask(
    "Властелин колец: Братство кольца",
    2011,
    "movie",
    "The Lord of the Rings: The Fellowship of the Ring",
)


def test_a_release_year_later_than_the_article_is_a_reissue_of_the_same_picture() -> None:
    """Расширенная версия выходит отдельной раздачей и пишет год издания, а не выхода."""
    assert reissued(RING, FELLOWSHIP, {})


def test_a_year_that_only_wikidata_names_counts_the_same_way() -> None:
    """Английские категории про год молчат чаще русских, и год добирает SPARQL."""
    quiet = FELLOWSHIP._replace(years=frozenset())
    assert reissued(RING, quiet, {"Q127367": {2001}})


def test_a_namesake_whose_name_does_not_match_exactly_is_refused() -> None:
    """🔴 Контрпример: «Аниматрица» 2003-го приезжала под «Возвращение к источнику» 2004.

    Имя статьи там не совпадало с оригинальным именем раздачи вовсе, и совпадение строк -
    ровно тот признак, которым перевыпуск отличается от тёзки.
    """
    ask = Ask("Аниматрица", 2003, "movie", "The Animatrix")
    source = Dated("Final Flight of the Osiris", "Q7", frozenset({2003}), frozenset({"movie"}))
    assert not reissued(ask, source, {})


def test_a_picture_without_an_original_name_is_refused() -> None:
    """Пустое оригинальное имя не совпадает ни с чем: сравнивать тут нечего."""
    assert not reissued(RING._replace(original=""), FELLOWSHIP, {})


def test_a_year_earlier_than_the_article_is_not_a_reissue() -> None:
    """Переиздают вышедшее, а не будущее: обратная сторона допуска остаётся закрытой."""
    assert not reissued(RING._replace(year=1999), FELLOWSHIP, {})


def test_the_year_of_the_article_itself_is_left_to_the_plain_check() -> None:
    """Совпавший год - работа :func:`fits_ask`, и второй ответ на него тут лишний."""
    assert not reissued(RING._replace(year=2001), FELLOWSHIP, {})


def test_a_series_has_its_own_stretch_and_does_not_get_this_one() -> None:
    """🔴 Перезапуск под тем же именем («Battlestar Galactica» 1978 и 2004) вёл бы сюда
    картинку старого сериала, а у сериала растяжение своё - срок показа."""
    ask = Ask("Звёздный крейсер «Галактика»", 2004, "tv", "Battlestar Galactica")
    old = Dated("Battlestar Galactica", "Q9", frozenset({1978}), frozenset({"tv"}))
    assert not reissued(ask, old, {})


def test_an_article_that_never_calls_itself_a_film_is_refused() -> None:
    """Молчание категорий тут отказ: статья про событие несёт не постер, а снимок."""
    thing = Dated("The Lord of the Rings", "Q15228", frozenset({1954}), frozenset())
    assert not reissued(RING._replace(original="The Lord of the Rings"), thing, {})


def test_an_article_that_names_no_year_at_all_is_refused() -> None:
    """Неподтверждённый год - отказ, и перевыпуск этого правила не отменяет."""
    assert not reissued(RING, FELLOWSHIP._replace(years=frozenset()), {})
