"""Порт следа: молчание по умолчанию и именной словарь событий."""

from __future__ import annotations

from torrcast.ports.journal import Journal, _Silent, install, journal


def test_without_a_root_the_journal_is_silent_and_not_a_failure() -> None:
    """Прогон без композиционного корня не заводит файлов и не падает."""
    install(_Silent())
    port: Journal = journal()

    port.emit("search", "query", raw=1)
    port.segment(slot=1, mb=2.0, sent=0.1, wait=0.0, src="pack")

    assert port.records() == []
    assert port.session_id() == ""


def test_an_installed_sink_gets_every_event() -> None:
    """Назначенный приёмник получает и свободное событие, и именное."""

    class _Spy:
        def __init__(self) -> None:
            self.seen: list[tuple[str, str]] = []

        def emit(self, phase: str, event: str, **fields: object) -> None:
            self.seen.append((phase, event))

        def dark(self, pos: float, why: str, shown: bool = True) -> None:
            self.seen.append(("play", "dark"))

    spy = _Spy()
    install(spy)  # type: ignore[arg-type]

    journal().emit("play", "start")
    journal().dark(pos=1.0, why="источник умер")

    assert spy.seen == [("play", "start"), ("play", "dark")]
    install(_Silent())
