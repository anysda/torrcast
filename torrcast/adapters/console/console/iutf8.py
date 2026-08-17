"""Бит ``IUTF8`` во флагах ввода pty - отдельной функцией ради тайпчека.

Спрашивает его только включение режима терминала (:func:`terminal`)."""

from __future__ import annotations


def iutf8() -> int:
    """Бит ``IUTF8`` во флагах ввода pty. Отдельной функцией — mypy не знает его на всех
    платформах, а нам он нужен ровно на Linux.
    """
    import termios

    return int(getattr(termios, "IUTF8", 0o40000))
