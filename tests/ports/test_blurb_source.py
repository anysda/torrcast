"""Проверяет контракт добора справки к меню и поведение его фейка."""

from tests.fakes.blurb_source import FakeBlurbSource
from torrcast.domain.facts.fact import Fact
from torrcast.ports.blurb_source import BlurbSource


def test_fake_records_the_walk_and_hands_the_answer_to_ready() -> None:
    """Фейк помнит, о ком ходили спрашивать, и отдаёт добытое ``ready``."""
    cars: dict[tuple[str, int | None], Fact] = {("Тачки", 2006): Fact(about="о гонках")}
    fake = FakeBlurbSource(lambda wanted: cars)
    port: BlurbSource = fake
    seen: list[dict[tuple[str, int | None], Fact]] = []
    assert port.fetch([("Тачки", 2006)], ready=seen.append) == cars
    assert fake.walks == [[("Тачки", 2006)]]
    assert seen == [cars]
