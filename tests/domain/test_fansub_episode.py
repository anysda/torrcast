"""Зеркало :mod:`torrcast.domain.fansub_episode`: серия в имени фансаб-раздачи."""

from torrcast.domain.fansub_episode import _fansub_episode


def test_the_name_and_the_episode_are_read_out_of_the_bracketed_form() -> None:
    """Аниме-раздачи пишут серию так: группа в скобках, имя, тире, номер."""
    found = _fansub_episode("[SubsPlease] Naruto - 12 [1080p]")

    assert found is not None
    assert found.group("name") == "Naruto"
    assert found.group("episode") == "12"


def test_a_year_in_the_name_makes_it_not_an_episode() -> None:
    """С годом это фильм, и «- 12» в нём - что угодно, только не номер серии."""
    assert _fansub_episode("[SubsPlease] Naruto 2001 - 12 [1080p]") is None


def test_a_name_without_the_bracketed_group_is_not_this_form() -> None:
    assert _fansub_episode("Naruto - 12 [1080p]") is None


def test_a_padded_number_is_an_episode_even_without_the_group() -> None:
    """🔴 TC-969. Раздачи без группы впереди разводили одну картину по крошкам: каждая
    серия становилась своей картиной, и в меню стояло тринадцать мёртвых строк."""
    found = _fansub_episode("Shoujo kara Shoujo e... - 02 [Sub Esp] [1080p]")

    assert found is not None
    assert found.group("name") == "Shoujo kara Shoujo e..."
    assert found.group("episode") == "02"


def test_the_name_is_read_past_a_bracket_standing_in_the_middle_of_it() -> None:
    """Без группы впереди скобка сплошь и рядом стоит ПОСРЕДИ имени, и по сырому тексту
    имя до номера не дочитывается вовсе."""
    found = _fansub_episode("Shoujo kara Shoujo e... (少女から娼女へ...) OVA - 02 [3C20A607]")

    assert found is not None
    assert found.group("episode") == "02"


def test_a_bare_number_without_a_leading_zero_stays_part_of_the_name() -> None:
    """🔴 Граница правила: «Korashime - 2» это продолжение, а не вторая серия. Серии
    нумеруют «- 02», продолжения так не нумеруют никогда."""
    assert _fansub_episode("Korashime - 2 [1080p]") is None


def test_a_three_digit_number_is_a_piece_of_the_name_not_an_episode() -> None:
    """🔴 Вторая половина границы - ШИРИНА. Трёхзначный ведущим нулём неотличим от куска
    имени, а год, который спас бы разбор, у раздачи есть не всегда. Замерено: на
    замороженной выдаче и на фикстурах трёхзначных этой раскладкой взято НОЛЬ."""
    assert _fansub_episode("James Bond - 007") is None
    assert _fansub_episode("James Bond - 007 [1080p]") is None


def test_a_three_digit_episode_still_reads_when_the_group_vouches_for_it() -> None:
    """Плата за ширину не задевает длинный сериал: там улику даёт группа, и подпорка
    ведущим нулём не нужна вовсе."""
    found = _fansub_episode("[Erai-raws] One Piece - 007 [1080p]")

    assert found is not None
    assert found.group("episode") == "007"
