"""Порт следа: молчание по умолчанию и именной словарь событий."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.file_journal import FileJournal
from torrcast.ports.journal.journal import Journal
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install, journal


def test_without_a_root_the_journal_is_silent_and_not_a_failure() -> None:
    """Прогон без композиционного корня не заводит файлов и не падает."""
    install(Silent())
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


def test_the_sink_of_the_previous_test_does_not_outlive_it() -> None:
    """Отрицательная проба возврата: два теста выше ставили своё - здесь снова боевая лента.

    Проба стоит ИМЕННО здесь и ИМЕННО после них: порт - это модульная переменная процесса,
    и утечка видна только следующему тесту. Раньше её ловила лишь раскладка xdist, да и то
    через раз, - четыре теста показа падали на пустой ленте, а выглядело это как плавающий
    тест. Если проба покраснела, значит фикстура ``_ports_restored`` перестала возвращать
    чужое, и красным станет случайный тест где-то далеко отсюда.
    """
    assert isinstance(journal(), FileJournal)
