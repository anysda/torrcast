"""Проверяет контракт хранилища родни и поведение его фейка."""

from tests.fakes.kin_store import FakeKinStore
from torrcast.domain.facts.kin import Kin
from torrcast.ports.kin_store import KinStore


def test_unasked_entity_reads_as_none_and_written_one_reads_back() -> None:
    """``None`` значит «не спрашивали», а записанное читается тем же идентификатором."""
    fake = FakeKinStore()
    port: KinStore = fake
    assert port.read_kin("Q105598") is None
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    port.write_kin("Q105598", found)
    assert port.read_kin("Q105598") == found
    assert port.read_kin("Q1") is None
    assert fake.written == [("Q105598", found)]


def test_an_empty_shelf_is_written_and_reads_back_empty_and_not_as_unasked() -> None:
    """Пустой список - тоже ответ: франшизы нет, а не «не спрашивали»."""
    fake = FakeKinStore()
    fake.write_kin("Q1", [])
    assert fake.read_kin("Q1") == []
