"""Зеркало :mod:`torrcast.domain.nearest_group`: какая группа ближе к спрошенному слову."""

from torrcast.domain.nearest_group import _nearest_group
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _group(title: str, year: int, copies: int) -> list[Picture]:
    return [
        Picture(
            title=title,
            year=year,
            releases=[Release(raw_name=title, title=title) for _ in range(copies)],
        )
    ]


#: Две группы, дописывающие к «властелин» ровно по одному своему слову: «мира» короче
#: «колец» на букву, а раздач у неё в двадцать четыре раза меньше.
GROUPS = {
    "властелин-мира": _group("Властелин мира", 1961, 2),
    "властелин-колец": _group("Властелин колец", 2001, 48),
    "властелин-тайной-горы": _group("Властелин тайной горы", 2022, 1),
}


def test_the_shorter_name_does_not_outweigh_the_fuller_catalogue() -> None:
    """🔴 TC-1025. Слов дописано поровну - решает вес, а не длина слага."""
    assert _nearest_group("властелин", GROUPS, list(GROUPS)) == "властелин-колец"


def test_fewer_added_words_wins_over_any_weight() -> None:
    """Лишнее слово весом не покупается: два слова дальше одного, сколько ни раздач."""
    groups = dict(GROUPS)
    groups["властелин-тайной-горы"] = _group("Властелин тайной горы", 2022, 900)

    assert _nearest_group("властелин", groups, list(groups)) == "властелин-колец"


def test_the_only_hit_is_the_answer() -> None:
    assert _nearest_group("властелин", GROUPS, ["властелин-мира"]) == "властелин-мира"


def test_equal_words_and_equal_weight_answer_the_same_every_run() -> None:
    """Два замера одного корпуса сравнимы, только если выбор не пляшет от прогона."""
    groups = {"брат-один": _group("Брат один", 1997, 3), "брат-два": _group("Брат два", 2000, 3)}

    assert _nearest_group("брат", groups, list(groups)) == _nearest_group(
        "брат", groups, list(reversed(list(groups)))
    )
