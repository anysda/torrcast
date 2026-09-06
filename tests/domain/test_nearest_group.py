"""Зеркало :mod:`torrcast.domain.nearest_group`: какая группа ближе к спрошенному слову."""

from torrcast.domain.nearest_group import _nearest_group
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _by_itself(groups: dict[str, list[Picture]]) -> dict[str, str]:
    """Одноязычный каталог: группа найдена под собственным слагом."""
    return {key: key for key in groups}


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
    assert _nearest_group("властелин", GROUPS, _by_itself(GROUPS)) == "властелин-колец"


def test_fewer_added_words_wins_over_any_weight() -> None:
    """Лишнее слово весом не покупается: два слова дальше одного, сколько ни раздач."""
    groups = dict(GROUPS)
    groups["властелин-тайной-горы"] = _group("Властелин тайной горы", 2022, 900)

    assert _nearest_group("властелин", groups, _by_itself(groups)) == "властелин-колец"


def test_the_only_hit_is_the_answer() -> None:
    lone = {"властелин-мира": "властелин-мира"}

    assert _nearest_group("властелин", GROUPS, lone) == "властелин-мира"


def test_equal_words_and_equal_weight_answer_the_same_every_run() -> None:
    """Два замера одного корпуса сравнимы, только если выбор не пляшет от прогона."""
    groups = {"брат-один": _group("Брат один", 1997, 3), "брат-два": _group("Брат два", 2000, 3)}

    assert _nearest_group("брат", groups, _by_itself(groups)) == _nearest_group(
        "брат", groups, _by_itself(dict(reversed(list(groups.items()))))
    )


#: 🔴 TC-1064. Двуязычный каталог: «Матрицу» индексер отдаёт под русским названием, и
#: спрошенное латиницей слово живёт не в слаге её группы, а во втором её имени.
BILINGUAL = {
    "матрица": _group("Матрица", 1999, 58),
    "the-animatrix": _group("The Animatrix", 2003, 2),
    "l-matrix": _group("L-MATRIX", 2011, 1),
}


def test_a_group_found_by_its_other_name_takes_part_in_the_ranking() -> None:
    """Группу берут по её значению: имя находки лишь дорога к ней, мерят саму группу."""
    hits = {"the-matrix": "матрица", "the-animatrix": "the-animatrix", "l-matrix": "l-matrix"}

    assert _nearest_group("matrix", BILINGUAL, hits) == "матрица"


def test_a_long_second_name_does_not_push_its_group_behind_a_namesake() -> None:
    """Мерка ставится на ГРУППУ: длина дороги к ней не делает её дальше от запроса.

    «Матрицу» каталог отдал под «The Matrix Resurrections» - имя из трёх слов против
    двух у «L-MATRIX». Мерь мы имя, спрошенное «matrix» ушло бы в однофамильца на одну
    раздачу мимо франшизы на пятьдесят восемь.
    """
    hits = {"the-matrix-resurrections": "матрица", "l-matrix": "l-matrix"}

    assert _nearest_group("matrix", BILINGUAL, hits) == "матрица"
