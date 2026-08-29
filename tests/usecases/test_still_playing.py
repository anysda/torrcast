"""Зеркало приговора о живом показе: когда строка из журнала значит «зритель смотрит»."""

from __future__ import annotations

from torrcast.usecases.screen_line import screen_line
from torrcast.usecases.still_playing import still_playing

#: Куда завели показ в происшествии TC-884: «Домохозяйки» s1e8, 0:26:58.
_LANDED = 26 * 60 + 58.0
#: Длительность серии оттуда же.
_WHOLE = 44 * 60.0


def test_a_pointer_that_moved_past_the_landing_point_proves_the_picture() -> None:
    """Указатель ушёл с места захода - зритель видит кадры, и это не «показ не начался»."""
    assert still_playing(screen_line("[с]", _LANDED + 1.0, _WHOLE, "PLAYING"), _LANDED)
    assert still_playing(screen_line("[с]", _LANDED + 324.0, _WHOLE, "PAUSED"), _LANDED), (
        "паузу поставил зритель - кадр на экране его же и остался"
    )


def test_a_pointer_standing_where_the_show_was_landed_proves_nothing() -> None:
    """Слово приёмника без сдвига указателя картинкой не является.

    Приёмник объявляет себя играющим раньше первого кадра и до него держит указатель на
    месте захода. Прими приговор это слово за картинку - он перестал бы отличать идущий
    показ от не начавшегося вовсе, и чёрный экран висел бы до утра.
    """
    assert not still_playing(screen_line("[с]", _LANDED, _WHOLE, "PLAYING"), _LANDED)
    assert not still_playing(screen_line("[с]", _LANDED + 324.0, _WHOLE, "IDLE"), _LANDED)


def test_the_line_of_the_darkness_is_not_a_screen() -> None:
    """Строка темноты - не отчёт об экране: числа в ней про другое, и читать их нельзя.

    В темноте показ отчитывается своей строкой нарочно
    (:func:`torrcast.usecases.revive_playback._screen._report`): позицией и запасом там
    назывался бы чёрный экран.
    """
    dark = "[сеанс 7] темнота 0:01:40 (сети нет) - картинки нет; поднимал 1 из 3"

    assert not still_playing(dark, 0.0)


def test_the_bookkeeping_of_systemd_is_not_a_screen_either() -> None:
    """Послесловие systemd показом не является - на нём приговор молчит, а не гадает."""
    assert not still_playing("torrcast-play.service: Consumed 5.884s CPU time", 0.0)
    assert not still_playing("в журнале пусто", 0.0)
