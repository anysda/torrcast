"""Выбор таблицы серий пропускает раздачу, которая исчерпала попытки."""

from dataclasses import dataclass, field

from torrcast.domain.release import Release
from web.answered_episode import answered_episode
from web.episode_lookup import UNAVAILABLE


@dataclass
class _Tables:
    values: dict[str, list[list[int]] | None]
    asked: list[str] = field(default_factory=list)

    def table(self, release: Release, _base_url: str) -> list[list[int]] | None:
        self.asked.append(release.magnet)
        return self.values[release.magnet]


def test_the_next_release_is_used_only_after_the_first_one_is_unavailable() -> None:
    dead = Release(raw_name="Show S01", title="Show", magnet="magnet:dead")
    live = Release(raw_name="Show S01", title="Show", magnet="magnet:live")
    tables = _Tables({dead.magnet: UNAVAILABLE, live.magnet: [[1, 1]]})

    table, chosen = answered_episode(
        [dead, live], tables, "http://ts", lambda left: left[0] if left else None, dead
    )

    assert (table, chosen, tables.asked) == ([[1, 1]], live, [dead.magnet, live.magnet])
