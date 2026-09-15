"""Зеркало :mod:`torrcast.domain.facts.pool_passport`: статья справки против картины выдачи."""

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.pool_passport import pool_passport
from torrcast.domain.facts.settings import SOURCE_MAP
from torrcast.domain.picture import Picture
from torrcast.domain.slugify import slugify

_MAP = {
    "мы": [MapPicture("Мы", 2019, False, "Us", 399488)],
    "восхождение": [
        MapPicture("Восхождение", 1977, False, "Voskhozhdeniye", 12596),
        MapPicture("Восхождение", 2019, False, "The Climb", 5636),
    ],
}


def _known(title: str) -> list[MapPicture]:
    return _MAP.get(slugify(title), [])


def test_an_article_about_another_namesake_yields_to_the_proven_picture() -> None:
    """🔴 Справка знала «Мы» как «Mēs?» (1989), а выдача и карта - как Us (2019)."""
    article = Origin(title="Mēs?", year=1989, name="Мы")

    about = pool_passport(article, "Мы", [Picture(title="Мы", year=2019)], _known)

    assert about == Origin(title="Us", year=2019, name="Мы", source=SOURCE_MAP)


def test_an_article_whose_year_is_in_the_pool_keeps_the_passport() -> None:
    article = Origin(title="Us", year=2019, name="Мы")

    assert pool_passport(article, "Мы", [Picture(title="Мы", year=2019)], _known) is article


def test_an_article_the_map_knows_better_keeps_the_passport() -> None:
    """«Восхождение» Шепитько (12 596 голосов) держит имя против «The Climb» (5 636)."""
    article = Origin(title="Voskhozhdeniye", year=1977, name="Восхождение")
    pool = [Picture(title="Восхождение", year=2019)]

    assert pool_passport(article, "Восхождение", pool, _known) is article


def test_the_boundary_a_silent_map_leaves_the_article_as_it_was() -> None:
    """⚠️ Граница: картины выдачи карта не знает - и паспорт ровно тот, что дала справка."""
    article = Origin(title="Mēs?", year=1989, name="Мы")

    assert pool_passport(article, "Мы", [Picture(title="Мы", year=2019)], lambda _: []) is article
    assert pool_passport(article, "Мы", [Picture(title="Мы", year=None)], _known) is article
    assert pool_passport(article, "Мы", [Picture(title="Мы нашли", year=2019)], _known) is article


def test_an_article_without_a_year_does_not_open_the_map() -> None:
    """Без года статья не спорит с пулом: карту читать незачем."""
    asked: list[str] = []

    def known(title: str) -> list[MapPicture]:
        asked.append(title)
        return []

    article = Origin(title="Mēs?", name="Мы")
    assert pool_passport(article, "Мы", [Picture(title="Мы", year=2019)], known) is article
    assert asked == []
