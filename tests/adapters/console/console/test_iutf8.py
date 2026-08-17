"""Бит ``IUTF8``: настоящий флаг ядра, а не выдуманное число."""

from __future__ import annotations

import termios

from torrcast.adapters.console.console.iutf8 import iutf8


def test_the_bit_is_the_one_the_kernel_knows() -> None:
    """Это тот самый флаг ввода pty, который чинит забой на кириллице.

    Ошибись здесь числом - и режим терминала выставлял бы посторонний бит: забой
    остался бы сломанным, а на экране появилось бы что-нибудь новое.
    """
    assert iutf8() == getattr(termios, "IUTF8", 0o40000)
    assert iutf8() == 0o40000, "значение флага в Linux, ради которого функция и заведена"


def test_the_bit_is_a_single_flag_and_not_a_mask_of_several() -> None:
    """Один бит: маской из нескольких он гасил бы соседние флаги режима."""
    assert bin(iutf8()).count("1") == 1
