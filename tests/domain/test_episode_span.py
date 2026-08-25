"""Зеркало :mod:`torrcast.domain.episode_span`: какие серии обещает имя раздачи."""

from torrcast.domain.episode_span import _episode_span


def test_a_named_range_gives_every_episode_inside_it() -> None:
    assert _episode_span("Сериал 5-8 серии") == (5, 6, 7, 8)


def test_a_count_out_of_a_total_starts_the_run_from_the_first_episode() -> None:
    """«1-12 из 24» - это выложенная половина: серии считаются от начала, а не от нуля."""
    assert _episode_span("Сериал (1-12 из 24)") == tuple(range(1, 13))


def test_a_name_that_promises_no_episodes_gives_none() -> None:
    assert _episode_span("Кино 1997 1080p") == ()


def test_a_backwards_range_is_not_a_range() -> None:
    """Конец раньше начала - это опечатка в имени, а не пустой сериал."""
    assert _episode_span("Сериал 8-5 серии") == ()
