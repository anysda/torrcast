"""Умолчание порта юнита показа: ничего не играет и никого не гасит."""

from torrcast.ports.show_unit import Idle, ShowUnit


def test_without_a_root_there_is_no_unit_and_that_is_not_a_failure() -> None:
    """Прогон без композиционного корня не имеет права дёргать службы хозяйской машины."""
    port: ShowUnit = Idle()

    assert not port.active()
    assert port.why() == ""
    assert port.key() == ""
    port.stop()

    assert not port.active(), "погасить у умолчания нечего, и живым оно не станет"
