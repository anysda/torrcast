"""Умолчание порта следа: принимает любое событие и не пишет ни байта."""

from torrcast.ports.journal import Journal, Silent


def test_a_named_event_of_the_silent_journal_is_silence_too() -> None:
    """Именное событие у молчания есть всегда: словарь событий растёт, умолчание - нет.

    Без этого каждая новая схема события (:mod:`torrcast.adapters.filesystem.trace_journal`)
    роняла бы прогон без композиционного корня - щуп, отдельный тест, - и умолчание
    приходилось бы дописывать вслед за лентой.
    """
    port: Journal = Silent()

    port.emit("search", "query", raw=1)
    port.mark("старт", секунды=0.5)
    port.segment(slot=1, mb=2.0, sent=0.1, wait=0.0, src="pack")
    port.warmth("греем", secs=1.0, dur=2.0, size=3)

    assert port.records() == []
    assert port.session_id() == ""
    assert port.start_session() == ""
    assert port.health() == (False, 0.0, 0)


def test_an_event_the_journal_never_heard_of_is_silence_as_well() -> None:
    """Отрицательная проба: умолчание молчит и на имя, которого в договоре нет."""
    silent = Silent()

    assert silent.никогда_такого_не_было(1, 2, три=3) is None
