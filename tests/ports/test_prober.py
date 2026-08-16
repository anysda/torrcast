"""Проверяет контракт чтения паспорта медиа и поведение фейка."""

from tests.fakes.prober import FakeProber
from torrcast.domain.media import Media
from torrcast.ports.prober import Prober


def test_fake_records_source_and_returns_media() -> None:
    media = Media(duration=42)
    fake = FakeProber(media)
    port: Prober = fake
    assert port.probe("http://source") == media
    assert fake.sources == ["http://source"]
