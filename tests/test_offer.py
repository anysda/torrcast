"""Хвост очереди родни не отменяет видимый экран."""

from collections.abc import Callable

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.offer import offer
from web.warm_cache import WarmCache


def test_related_offers_stay_behind_the_visible_screen() -> None:
    """Родня добавляется хвостом и не меняет порядок плиток в окне."""
    picture = Picture(title="Interstellar", year=2014, kind="movie")
    picture.releases = [Release(raw_name="Interstellar 2014 BDRip", title="Interstellar")]
    plan = Plan(picture=picture, ranked=list(picture.releases), runtime=8520.0, warn_mbit=12.0)
    asked: list[str] = []
    jobs: list[Callable[[], None]] = []

    def circle(query: str) -> list[Plan]:
        asked.append(query)
        return [plan]

    cache = WarmCache(circle=circle, blurbs=lambda _pictures: None, spawn=jobs.append)
    cache.ask(["Ludwig", "Kin"])

    offer(cache, ["Franchise"])
    for job in list(jobs):
        job()

    assert asked == ["Ludwig", "Kin", "Franchise"]
