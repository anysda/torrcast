"""Сезоны картины с раздачами в круге поиска: доказательство выхода серии без даты."""

from __future__ import annotations

from dataclasses import dataclass, field

from hass import released_seasons as module
from hass.released_seasons import released_seasons
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan

KEY = "tv:рик-и-морти:2013"


def _plan(key_title: str, seasons: tuple[int, ...]) -> Plan:
    releases = [
        Release(raw_name=f"Rick and Morty S{n:02d}", title=key_title, year=2013, season=n)
        for n in seasons
    ]
    picture = Picture(title=key_title, year=2013, kind="tv", releases=releases)
    return Plan(picture=picture, ranked=releases, runtime=1300.0, warn_mbit=16.0)


@dataclass
class _Pool:
    plans: list[Plan] | None
    hinted: list[str] = field(default_factory=list)
    asked: int = 0

    def ready(self, _query: str) -> list[Plan] | None:
        self.asked += 1
        return self.plans

    def hint(self, query: str) -> int:
        self.hinted.append(query)
        return 1


def test_a_cold_pool_is_warmed_and_proves_nothing_yet() -> None:
    module._seen.clear()
    pool = _Pool(None)
    assert released_seasons(KEY, "rick and morty", pool) is None
    assert pool.hinted == ["rick and morty"], "круг греется фоном, а не в опросе состояния"


def test_seasons_of_the_same_picture_are_remembered() -> None:
    module._seen.clear()
    plan = _plan("Рик и Морти", (8, 9))
    assert plan.picture.key == KEY
    pool = _Pool([_plan("Рик и Морти: Аниме", (1, 2, 3, 10)), plan])
    first = released_seasons(KEY, "rick and morty", pool, clock=lambda: 0.0)
    again = released_seasons(KEY, "rick and morty", pool, clock=lambda: 60.0)
    assert first == again == (8, 9), "сезоны чужой картины круга не в счёт"
    assert pool.asked == 1, "опрос каждую секунду не пересобирает круг"
