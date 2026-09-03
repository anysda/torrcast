"""Зеркало :mod:`torrcast.domain.facts.poster_names`: имена, под которыми ищут статью."""

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.poster_names import poster_names


def test_the_title_itself_stands_first_and_the_qualified_name_follows() -> None:
    """Порядок тут - порядок доверия: первым спрашивается то, чем картину и подписали."""
    names = poster_names(Ask("Матрица", 1999, "movie"))
    assert names[0] == "Матрица"
    assert "Матрица (фильм, 1999)" in names


def test_a_pack_of_films_is_also_asked_by_the_name_of_its_first_part() -> None:
    """Сборник называет себя перечнем частей, а статья у него - статья первой части."""
    names = poster_names(Ask("Матрица, Матрица: Перезагрузка, Матрица: Революция", 1999, "movie"))
    assert "Матрица" in names, "голова сборника спрошена отдельным именем"


def test_a_title_with_a_comma_is_not_cut_down_to_a_stranger_of_the_same_year() -> None:
    """🔴 Голова обязана повториться дальше в названии, иначе это не сборник (TC-957).

    Без этого условия «Титаник, любовь и катастрофа» спрашивался бы под именем
    «Титаник» - и получал бы статью кэмероновского фильма ТОГО ЖЕ года, то есть мимо
    всякой сверки: человеку отличить такую картинку нечем.
    """
    names = poster_names(Ask("Титаник, любовь и катастрофа", 1997, "movie"))
    assert "Титаник" not in names, f"голова отрезана у несборника: {names}"
