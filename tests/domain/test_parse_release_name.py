"""Зеркало :mod:`torrcast.domain.parse_release_name`: имя раздачи, разобранное на поля."""

from torrcast.domain.parse_release_name import _bare_episode_span, parse_release_name


def test_the_whole_name_falls_apart_into_the_fields_the_choice_needs() -> None:
    """Отбор судит раздачу этими полями, а трекер отдаёт их одной строкой."""
    found = parse_release_name("Брат / Brother (1997) BDRip 1080p x264 [Дубляж]")

    assert found.title == "Брат"
    assert found.original == "Brother"
    assert found.year == 1997
    assert found.quality == "1080p"
    assert found.codec == "H.264"
    assert found.source == "BDRip"
    assert found.voices == ("Дубляж",)


def test_a_bare_name_leaves_the_fields_unnamed_instead_of_guessed() -> None:
    """Имя молчит - поле пустое: догадка тут стоила бы зрителю не той картины."""
    found = parse_release_name("Брат")

    assert found.title == "Брат"
    assert found.year is None
    assert found.quality is None
    assert found.codec is None


def test_a_bare_run_of_episodes_is_read_as_a_series() -> None:
    """«1-12» в хвосте длинного латинского имени - это серии, а не номер части."""
    assert _bare_episode_span("The Big Bang Theory 1-12") == tuple(range(1, 13))


def test_a_short_name_with_the_same_tail_is_not_a_run_of_episodes() -> None:
    """У короткого имени «1-2» - это сборник частей, и серий тут не обещано."""
    assert _bare_episode_span("Кино 1-12") == ()
