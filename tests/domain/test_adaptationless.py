"""Зеркало :mod:`torrcast.domain.adaptationless`: примета экранизации против вида."""

from torrcast.domain.adaptationless import _adaptationless


def test_the_adaptation_mark_is_dropped_wherever_it_stands() -> None:
    """«X The Animation» и «X» - одна работа, а выдача звала её то так, то этак."""
    assert _adaptationless("sakusei-byoutou-the-animation") == "sakusei-byoutou"
    assert _adaptationless("the-animation-sakusei-byoutou") == "sakusei-byoutou"
    assert _adaptationless("love-me-kaede-to-suzu-the-anime") == "love-me-kaede-to-suzu"


def test_a_number_behind_the_mark_is_an_episode_and_is_left_alone() -> None:
    """🔴 Этим правило и отличается от слова формы: за «Movie» стоит номер ЧАСТИ, а за
    «The Animation» - номер СЕРИИ, и снимать его тут не наше дело."""
    assert _adaptationless("sakusei-byoutou-the-animation-10") == "sakusei-byoutou-10"


def test_a_word_outside_the_closed_list_is_not_the_mark() -> None:
    """Голое «animation» стоит в живых именах само по себе, и списком бережётся примета."""
    assert _adaptationless("animation-runner-kuromi") == "animation-runner-kuromi"
    assert _adaptationless("the-animatrix") == "the-animatrix"


def test_a_key_made_of_the_mark_alone_is_kept_whole() -> None:
    """Пустого ключа не отдаём: снимать больше нечего, а ключ нужен."""
    assert _adaptationless("the-animation") == "the-animation"
