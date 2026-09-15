"""Checks the minute budget of Wikipedia requests on a fake clock."""

from torrcast.adapters.wiki.minute_budget import (
    BACKGROUND_PER_MINUTE,
    MINUTE,
    UPLOAD_HOST,
    MinuteBudget,
)

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


def test_api_sites_share_one_minute_and_one_quiet_window() -> None:
    """A 429 of one Wikipedia quiets Wikidata too; a minute spent on ru holds en."""
    budget, clock = _spent()
    assert not budget.admit("www.wikidata.org", 0.0, foreground=False)
    fresh = MinuteBudget(clock, clock.pause)
    fresh.throttled("en.wikipedia.org", "9")
    assert not fresh.admit("www.wikidata.org", 0.0, foreground=False)
    assert not fresh.admit("ru.wikipedia.org", 0.0, foreground=False)


def test_image_files_keep_their_own_quiet_and_no_minute() -> None:
    """Files do not count against the API minute, and their 429 does not quiet the API."""
    budget, clock = _spent()
    assert budget.admit(UPLOAD_HOST, 0.0, foreground=False)
    budget.throttled(UPLOAD_HOST, "11")
    assert not budget.admit(UPLOAD_HOST, 0.0, foreground=False)
    fresh = MinuteBudget(clock, clock.pause)
    fresh.throttled(UPLOAD_HOST, "11")
    assert fresh.admit(_HOST, 0.0, foreground=False)
    assert fresh.calm_at() == clock.now + 11.0


def test_the_visible_list_goes_past_the_background_share_but_not_the_quiet() -> None:
    """An urgent ask uses the reserve, and a quiet longer than its wait refuses it at once."""
    budget, clock = _spent()
    assert budget.admit(_HOST, 0.0, foreground=False, urgent=True)
    start = clock.now
    assert not budget.troubled_since(start)
    budget.throttled(_HOST, "19")
    assert not budget.admit(_HOST, 8.0, foreground=False, urgent=True)
    assert clock.now == start, "an urgent ask sat out a quiet it could not outlive"
    assert budget.troubled_since(start)
    assert budget.calm_at() == start + 19.0


def test_a_local_refusal_is_trouble_not_an_answer() -> None:
    """A background ask refused by the spent minute marks the trouble clock."""
    budget, clock = _spent()
    start = clock.now
    assert not budget.troubled_since(start)
    assert not budget.admit(_HOST, 0.0, foreground=False)
    assert budget.troubled_since(start)
