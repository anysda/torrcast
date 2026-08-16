"""Проверяет контракт консоли и поведение её фейка."""

from tests.fakes.console import FakeConsole
from torrcast.ports.console import Console


def test_fake_records_dialogue() -> None:
    fake = FakeConsole(["answer"])
    port: Console = fake
    assert port.ask("question", "default") == "answer"
    port.write("message")
    assert (fake.questions, fake.messages) == ([("question", "default")], ["message"])
