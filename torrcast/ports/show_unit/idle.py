"""Юнита нет: прогон без композиционного корня ничего не играет и никого не гасит."""


class Idle:
    """Умолчание порта юнита показа: молчит на все вопросы и гасить ему нечего."""

    def active(self) -> bool:
        return False

    def why(self) -> str:
        return ""

    def stop(self) -> None:
        return None

    def key(self) -> str:
        return ""
