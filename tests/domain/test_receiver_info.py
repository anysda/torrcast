"""Зеркало :mod:`torrcast.domain.receiver_info`: найденный приёмник и его имя в меню."""

from torrcast.domain.receiver_info import ReceiverInfo


def test_the_network_identity_is_kept_as_it_was_found() -> None:
    """По адресу показ и стучится, а имя человек читает в меню."""
    found = ReceiverInfo("TV", "192.0.2.1")

    assert (found.name, found.address) == ("TV", "192.0.2.1")


def test_the_menu_calls_the_receiver_by_its_name() -> None:
    assert ReceiverInfo("Гостиная", "192.0.2.1", "Q70D").title == "Гостиная"


def test_a_nameless_receiver_is_called_by_its_model() -> None:
    """Имя приёмник отдаёт не всегда, а выбирать его человеку всё равно надо."""
    assert ReceiverInfo("", "192.0.2.1", "Q70D").title == "Q70D"


def test_a_receiver_that_said_nothing_about_itself_is_still_a_receiver() -> None:
    """Пустая строка в меню хуже честного слова: адрес рядом, и человек узнаёт свой."""
    assert ReceiverInfo("", "192.0.2.1").title == "приёмник"
