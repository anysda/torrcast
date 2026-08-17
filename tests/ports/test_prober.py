"""Проверяет контракт чтения паспорта медиа и поведение фейка."""

from tests.fakes.prober import FakeProber
from torrcast.domain.media import Media
from torrcast.ports.prober import Prober


def test_fake_records_source_and_returns_media() -> None:
    media = Media(duration=42)
    fake = FakeProber(media)
    port: Prober = fake
    assert port("http://source") == media
    assert fake.sources == ["http://source"]


def test_the_deadline_reaches_the_source() -> None:
    """Срок ответа - часть вопроса: без него ожидание паспорта было бы вечным."""
    fake = FakeProber(Media(duration=42))
    port: Prober = fake
    port("http://source", timeout=7.0)
    assert fake.timeouts == [7.0]
