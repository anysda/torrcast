"""Совместимая передача вопроса консольному порту; зовут её прежние части монолита."""

from __future__ import annotations

from torrcast.usecases.rank.configure import _console_port


def ask(question: str, count: int, default: int = 1) -> int:
    """Совместимо передать вопрос консольному порту."""
    return _console_port().choose(question, count, default)
