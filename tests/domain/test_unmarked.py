"""Зеркало :mod:`torrcast.domain.unmarked`: чем маркер вида отличается от имени."""

from torrcast.domain.unmarked import _unmarked


def test_a_trailing_kind_marker_is_dropped() -> None:
    """«Токийский гуль ОВА» это тот же сериал: хвост говорит о виде, а не о картине."""
    assert _unmarked("токийский-гуль-ова") == "токийский-гуль"
    assert _unmarked("моб-психо-100-тв") == "моб-психо-100"
    assert _unmarked("bleach-movie") == "bleach"


def test_a_leading_kind_marker_is_dropped_too() -> None:
    """Раздача ставит маркер и в начало: «OVA Tokyo Ghoul» это «Tokyo Ghoul»."""
    assert _unmarked("ova-tokyo-ghoul") == "tokyo-ghoul"


def test_a_word_in_the_middle_is_a_name_and_stays() -> None:
    """Середину не трогаем: там стоит имя, и стрижка внутри слепила бы чужие ключи."""
    assert _unmarked("нечто-фильм-о-любви") == "нечто-фильм-о-любви"


def test_a_word_outside_the_closed_list_is_not_a_marker() -> None:
    """Закрытый список и есть ограждение: за ним «Оно приходит ночью» неотличимо от «Оно»."""
    assert _unmarked("оно-приходит-ночью") == "оно-приходит-ночью"
    assert _unmarked("титаник-666") == "титаник-666"
    assert _unmarked("друзья-с-колледжа") == "друзья-с-колледжа"
    assert _unmarked("унесенные-призраками-фильм-о-фильме") == "унесенные-призраками-фильм-о-фильме"


def test_a_key_made_of_markers_alone_is_kept_whole() -> None:
    """Пустого ключа не отдаём: «ova» это всё, что о картине сказано, и стричь нечего."""
    assert _unmarked("ova") == "ova"
