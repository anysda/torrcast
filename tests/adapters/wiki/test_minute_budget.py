"""Checks the minute budget of Wikipedia requests on a fake clock."""

from torrcast.adapters.wiki.minute_budget import BACKGROUND_PER_MINUTE, MINUTE, MinuteBudget

_HOST = "ru.wikipedia.org"


class _Clock:
    """A clock that moves only when the budget pauses."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.pauses: list[float] = []

    def __call__(self) -> float:
        return self.now

    def pause(self, seconds: float) -> None:
        self.pauses.append(seconds)
        self.now += seconds


def _spent() -> tuple[MinuteBudget, _Clock]:
    clock = _Clock()
    budget = MinuteBudget(clock, clock.pause)
    assert all(budget.admit(_HOST, 0.0, foreground=False) for _ in range(BACKGROUND_PER_MINUTE))
    return budget, clock


def test_a_click_passes_a_minute_the_background_has_spent() -> None:
    """The background stops at its share, a card request still goes at once."""
    budget, clock = _spent()
    assert not budget.admit(_HOST, 1.2, foreground=False)
    assert budget.admit(_HOST, 1.2, foreground=True)
    assert clock.now <= 1000.0 + 1.2 + 0.01


def test_the_background_waits_for_the_minute_to_free_a_slot() -> None:
    """A background request with enough patience goes when its oldest neighbour ages out."""
    budget, clock = _spent()
    clock.now += MINUTE - 2.0
    assert budget.admit(_HOST, 4.0, foreground=False)
    assert clock.now == 1000.0 + MINUTE


def test_a_429_quiets_the_background_for_its_retry_after() -> None:
    """After a 429 the background waits out ``Retry-After``; the card is not held."""
    clock = _Clock()
    budget = MinuteBudget(clock, clock.pause)
    budget.throttled(_HOST, "7")
    assert not budget.admit(_HOST, 3.0, foreground=False)
    assert budget.admit(_HOST, 0.0, foreground=True)
    assert budget.admit(_HOST, 5.0, foreground=False)
    assert clock.now == 1000.0 + 7.0
    assert budget.admit(_HOST, 0.0, foreground=False)


def test_sparql_is_not_counted_against_the_wikipedia_minute() -> None:
    """query.wikidata.org has its own limits: a spent Wikipedia minute does not hold it."""
    budget, clock = _spent()
    budget.throttled("query.wikidata.org", "30")
    assert budget.admit("query.wikidata.org", 0.0, foreground=False)
    assert not budget.admit("en.wikipedia.org", 0.0, foreground=False)
    assert clock.now == 1000.0
