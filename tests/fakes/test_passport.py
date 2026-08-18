"""Зеркало :mod:`tests.fakes.passport`."""

from tests.fakes.passport import FakePassport
from torrcast.domain.facts.origin import Origin


def test_fake_answers_the_known_title_and_records_the_question() -> None:
    known = Origin(title="Psycho", year=1960)
    fake = FakePassport({"психо": known})

    assert fake("психо") == known
    assert fake("нетакогофильма") == Origin()
    assert fake.asked == ["психо", "нетакогофильма"]
