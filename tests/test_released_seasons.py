"""Сезоны картины с раздачами в круге поиска: доказательство выхода серии без даты."""

from __future__ import annotations

from dataclasses import dataclass, field

from hass import released_seasons as module
from hass.released_seasons import released_seasons
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.circle_memory import CircleMemory

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


@dataclass
class _Memory:
    """Пул поверх настоящей памяти кругов: что она вернёт на отказ, то и прочтут сезоны."""

    memory: CircleMemory
    hinted: list[str] = field(default_factory=list)

    def ready(self, query: str) -> list[Plan] | None:
        return self.memory.plans(query)

    def hint(self, query: str) -> int:
        self.hinted.append(query)
        return 1


def test_a_circle_torn_by_the_network_is_not_remembered_as_no_seasons() -> None:
    module._seen.clear()
    now = [0.0]
    memory = CircleMemory(lambda: now[0], ttl=600.0)
    pool = _Memory(memory)
    memory.refuse("rick and morty", InfraError("indexers did not answer"))
    assert memory.plans("rick and morty") == [], "сорванный круг до срока сеть не переспрашивает"
    said = released_seasons(KEY, "rick and morty", pool, clock=lambda: now[0])
    assert said is None, "сорванный сетью круг прочитан как «сезонов нет»"
    now[0] = 61.0
    memory.keep("rick and morty", [_plan("Рик и Морти", (8, 9))])
    later = released_seasons(KEY, "rick and morty", pool, clock=lambda: now[0])
    assert later == (8, 9), "«не знаю» запомнилось на час и перекрыло пришедший круг"


def test_a_circle_that_found_nothing_is_still_no_seasons() -> None:
    module._seen.clear()
    memory = CircleMemory(lambda: 0.0, ttl=600.0)
    memory.refuse("rick and morty", NotFoundError("nothing"))
    assert released_seasons(KEY, "rick and morty", _Memory(memory), clock=lambda: 0.0) == ()
