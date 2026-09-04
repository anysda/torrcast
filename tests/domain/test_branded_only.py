"""Зеркало :mod:`torrcast.domain.branded_only`: витрина вещателя вместо имени картины."""

from torrcast.domain.branded_only import _branded_only
from torrcast.domain.split_titles import _split_titles


def test_the_showcase_of_a_channel_is_not_a_name_of_a_picture() -> None:
    """Живой случай: после косой черты стоит строка продавца, а не имя картины."""
    assert _branded_only("BBC. Discovery channel exclusive")


def test_a_channel_name_alone_is_not_yet_a_showcase() -> None:
    """🔴 «The Discovery» - настоящее имя картины 2017 года, и съесть его нечем."""
    assert not _branded_only("The Discovery")
    assert not _branded_only("Animal Planet")
    assert not _branded_only("Channel Zero")


def test_a_showcase_never_reaches_the_original_name_of_the_picture() -> None:
    """🔴 Точное оригинальное имя несёт вес: под ним ищется статья и сверяется год.

    Витрина, дошедшая до этого места, однажды совпала бы с чужой статьёй точно.
    """
    zone = "BBC. Паразиты. Съеденные заживо. Змеи / BBC. Discovery channel exclusive"
    assert _split_titles(zone) == ("BBC. Паразиты. Съеденные заживо. Змеи", None, ())


def test_a_real_original_name_next_to_a_channel_survives() -> None:
    """Вычёркивается витрина, а не всякая латиница рядом с каналом."""
    zone = "BBC: Паразиты в организме человека / Body snatchers"
    assert _split_titles(zone) == ("BBC: Паразиты в организме человека", "Body snatchers", ())
