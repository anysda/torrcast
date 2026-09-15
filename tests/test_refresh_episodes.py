"""Зеркало суточного обновления индекса серий: служба зовёт сборку сама, раз в сутки."""

from pathlib import Path

from hass.refresh_episodes import DAY, FIRST, refresh_episodes
from torrcast.domain.facts.settings import EPISODES_PATH, EPISODES_URL


def test_the_index_is_rebuilt_every_day_after_a_quiet_start() -> None:
    slept: list[float] = []
    built: list[tuple[str, Path]] = []

    def build(url: str, target: Path) -> bool:
        built.append((url, target))
        return True

    refresh_episodes(rounds=2, sleep=slept.append, build=build)

    assert slept == [FIRST, DAY, DAY]
    assert built == [(EPISODES_URL, EPISODES_PATH)] * 2
