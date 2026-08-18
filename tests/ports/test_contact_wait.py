"""Проверяет контракт отсрочки первого контакта на её настоящей реализации.

Фейка тут нет намеренно: договор держит ровно одна отсрочка
(:class:`torrcast.adapters.torrserver.contact_wait.ContactWait`), и корень сборки
(:func:`torrcast.runtime.wire.wire`) выдаёт стенду отбора именно её.
"""

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.contact_wait import ContactWait as TorrServerWait
from torrcast.ports.contact_wait import ContactWait


def test_the_wait_has_no_clock_until_the_release_is_asked_about() -> None:
    port: ContactWait = TorrServerWait(3.0, FakeClock(now=12.0))
    assert port.activated_at is None
    assert float(port) == 3.0


def test_the_clock_starts_once_and_the_second_question_does_not_move_it() -> None:
    """Прогрев начинается заранее, а часы идут от вопроса - и только от первого."""
    clock = FakeClock(now=12.0)
    port: ContactWait = TorrServerWait(3.0, clock)
    port.activate(6.0)
    clock.sleep(5.0)
    port.activate(9.0)
    assert port.activated_at == 12.0
