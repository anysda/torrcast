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


def test_a_bracketed_run_without_a_leading_zero_is_still_a_run() -> None:
    """«[1-26]» - та же линейка, что и «[01-26]»: ведущий ноль не обязателен."""
    assert _episode_span("Ковбой Бибоп [1-26] BDRip") == tuple(range(1, 27))


def test_a_collector_note_inside_the_brackets_does_not_hide_the_run() -> None:
    """Пометка сборника за концом линейки - «[01-12TV全集+OVA]» - сериям не мешает."""
    assert _episode_span("Фрирен [01-12TV全集+OVA] BDRip") == tuple(range(1, 13))


def test_a_parenthesised_run_is_a_run() -> None:
    """Круглые скобки несут линейку так же, как квадратные: «(27-40)»."""
    assert _episode_span("Наруто (27-40) HDTV") == tuple(range(27, 41))


def test_a_bracketed_year_span_is_not_an_episode_run() -> None:
    """«(1984 - 2020)» - годы сборника: четырёхзначное начало линейкой не считается."""
    assert _episode_span("Сборник (1984 - 2020) BDRip") == ()


def test_an_english_to_run_is_a_run() -> None:
    """«OVAs 1 to 4» - англоязычная линейка серий без слова «серия»."""
    assert _episode_span("Samurai X OVAs 1 to 4 BDRip") == (1, 2, 3, 4)
