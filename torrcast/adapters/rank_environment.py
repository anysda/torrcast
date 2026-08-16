# mypy: disable-error-code=no-any-return
"""Консольная среда сценария ранжирования."""

from importlib import import_module


class SystemRankEnvironment:
    """Связывает меню сценария с обычной консолью."""

    def write(self, message: str) -> None:
        print(message)

    def choose(self, question: str, count: int, default: int) -> int:
        return import_module("torrcast.console").ask(question, count, default=default)


environment = SystemRankEnvironment()
