"""Проверяет контракт хранилища паспортов и поведение его фейка."""

from tests.fakes.origin_store import FakeOriginStore
from torrcast.domain.facts.origin import Origin
from torrcast.ports.origin_store import OriginStore


def test_unasked_picture_reads_as_none_and_written_one_reads_back() -> None:
    """``None`` значит «не спрашивали», а записанное читается тем же ключом типа."""
    fake = FakeOriginStore()
    port: OriginStore = fake
    assert port.read("Тачки", False) is None
    paper = Origin(title="Cars", year=2006)
    port.write("Тачки", False, paper)
    assert port.read("Тачки", False) == paper
    assert port.read("Тачки", None) is None, "режим «оба типа» - свой ключ"
    assert fake.written == [("Тачки", False, paper)]
