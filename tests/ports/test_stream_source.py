"""Проверяет контракт источника показа и поведение его фейка."""

from tests.fakes.stream_source import FakeStreamSource
from torrcast.ports.stream_source import StreamSource


def test_a_healthy_source_answers_with_silence() -> None:
    """Пустая строка - это «источник в порядке», а не «спросить не удалось»."""
    port: StreamSource = FakeStreamSource(torrent_hash="abc")
    assert port.check() == ""


def test_the_trouble_is_named_and_the_question_is_counted() -> None:
    """Беда называется словами: показ различает просевший рой и умершую службу."""
    fake = FakeStreamSource(torrent_hash="abc", trouble="служба раздач не отвечает")
    port: StreamSource = fake
    assert port.check() == "служба раздач не отвечает"
    assert fake.checks == ["abc"], "вопрос задаётся источнику ровно один раз"


def test_the_magnet_stays_with_the_source_because_the_hash_alone_has_no_trackers() -> None:
    """Магнит и хэш живут на источнике порознь: вернуть раздачу может только магнит."""
    port: StreamSource = FakeStreamSource()
    port.torrent_hash, port.magnet, port.lost = "abc", "magnet:?xt=1", ""
    assert (port.torrent_hash, port.magnet, port.restored) == ("abc", "magnet:?xt=1", False)
