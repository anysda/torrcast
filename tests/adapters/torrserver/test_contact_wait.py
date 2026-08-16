"""Проверяет запуск отсрочки на часах порта."""

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.contact_wait import ContactWait


def test_активация_запоминает_монотонное_время_порта() -> None:
    clock = FakeClock(now=12.0)
    wait = ContactWait(3.0, clock)
    wait.activate(6.0)
    assert wait.activated_at == 12.0
    assert wait.seconds == 6.0
