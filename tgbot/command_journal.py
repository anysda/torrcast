"""Именные записи о командах чата и их исходах."""

from torrcast.ports.journal.slot import journal


def _incoming(command: str) -> None:
    """Записать принятую из своего чата команду."""
    journal().emit("telegram", "incoming", command=command)


def _replaced(command: str, occupied: str) -> None:
    """Записать, какой запрос вытеснен новым."""
    journal().emit("telegram", "replaced", command=command, occupied=occupied)


def _refused(command: str, occupied: str, detail: str = "") -> None:
    """Записать отказ вместе с работой, которая занимала полосу."""
    journal().emit("telegram", "refused", command=command, occupied=occupied, detail=detail)


incoming = _incoming
replaced = _replaced
refused = _refused
