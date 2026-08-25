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
