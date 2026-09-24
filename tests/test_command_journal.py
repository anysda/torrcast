"""Зеркало именных записей команд Telegram."""

from tests.fakes.journal import Tape
from tgbot.command_journal import _incoming, _refused, _replaced
from torrcast.ports.journal.slot import install


def test_command_events_name_the_new_and_occupying_requests(_ports_restored: None) -> None:
    tape = Tape()
    install(tape)

    _incoming("cast муха")
    _replaced("cast муха", "cast матрица")
    _refused("button", "cast муха", "меню устарело")

    assert tape.named("telegram/incoming") == [{"command": "cast муха"}]
    assert tape.named("telegram/replaced") == [{"command": "cast муха", "occupied": "cast матрица"}]
    assert tape.named("telegram/refused") == [
        {"command": "button", "occupied": "cast муха", "detail": "меню устарело"}
    ]
