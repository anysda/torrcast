"""Серии TVmaze: диск сутки, фоновое обновление, молчание сети не держит карточку."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.wiki.tvmaze_episodes import (
    CALLS,
    FRESH,
    RETRY,
    WINDOW,
    TvmazeEpisodes,
    _Pace,
)

SHOW = "https://api.tvmaze.com/lookup/shows?imdb=tt0000001"
EPISODES = "https://api.tvmaze.com/shows/7/episodes"


class _Net:
    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def __call__(self, url: str) -> object:
        self.asked.append(url)
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _now(value: list[float]) -> Callable[[], float]:
    return lambda: value[0]


def _sync(job: Callable[[], None]) -> None:
    job()


ANSWERS: dict[str, object] = {
    SHOW: {"id": 7},
    EPISODES: [
        {
            "season": 1,
            "number": 1,
            "airdate": "2010-01-01",
            "airstamp": "2010-01-01T20:00:00+00:00",
        },
        {"season": 1, "number": None, "airdate": "2010-02-01", "airstamp": ""},
        {"season": 2, "number": 1, "airdate": "2026-09-20", "airstamp": None},
    ],
}


def test_the_episodes_land_on_disk_and_answer_without_the_network(tmp_path: Path) -> None:
    net, now = _Net(ANSWERS), [1000.0]
    first = TvmazeEpisodes(lambda: tmp_path, net, _sync, _now(now))

    aired, pending = first.aired("tt0000001")

    assert not pending
    assert aired == {
        (1, 1): ("2010-01-01T20:00:00+00:00", "2010-01-01"),
        (2, 1): ("2026-09-20", "2026-09-20"),
    }, "спецвыпуск без номера не серия"
    later = TvmazeEpisodes(lambda: tmp_path, _Net({}), _sync, _now(now))
    assert later.aired("tt0000001") == (aired, False)


def test_a_stale_answer_is_served_at_once_and_refreshed_behind(tmp_path: Path) -> None:
    now, jobs = [1000.0], list[Callable[[], None]]()
    TvmazeEpisodes(lambda: tmp_path, _Net(ANSWERS), _sync, _now(now)).aired("tt0000001")
    now[0] += FRESH + 1
    net = _Net({SHOW: {"id": 7}, EPISODES: []})
    stale = TvmazeEpisodes(lambda: tmp_path, net, jobs.append, _now(now))

    aired, pending = stale.aired("tt0000001")

    assert (len(aired), pending, net.asked) == (2, False, [])
    jobs.pop()()
    assert stale.aired("tt0000001") == ({}, False)


def test_a_silent_network_is_pending_then_empty_until_the_retry(tmp_path: Path) -> None:
    now, jobs = [1000.0], list[Callable[[], None]]()
    net = _Net({SHOW: TimeoutError("silent")})
    catalogue = TvmazeEpisodes(lambda: tmp_path, net, jobs.append, _now(now))

    assert catalogue.aired("tt0000001", wait=0.01) == ({}, True)
    jobs.pop()()
    assert catalogue.aired("tt0000001") == ({}, False)
    assert (jobs, len(net.asked)) == ([], 1), "молчание переспрашивается не раньше RETRY"
    now[0] += RETRY + 1
    catalogue.aired("tt0000001")
    assert len(jobs) == 1


def test_a_series_tvmaze_does_not_know_is_an_empty_answer_kept_for_a_day(tmp_path: Path) -> None:
    net = _Net({SHOW: None})
    catalogue = TvmazeEpisodes(lambda: tmp_path, net, _sync, _now([1000.0]))

    assert catalogue.aired("tt0000001") == ({}, False)
    assert catalogue.aired("tt0000001") == ({}, False)
    assert net.asked == [SHOW]
    assert catalogue.aired("../../etc/passwd") == ({}, False)


def test_the_twenty_first_question_in_ten_seconds_waits_for_the_window() -> None:
    now, slept = [0.0], list[float]()

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    pace = _Pace(_now(now), sleep)
    for _ in range(CALLS):
        pace()
        now[0] += 0.1
    pace()

    assert len(slept) == 1
    assert abs(slept[0] - (WINDOW - CALLS * 0.1)) < 1e-9, "ждёт выхода первого из окна"
    now[0] += WINDOW
    pace()
    assert len(slept) == 1, "окно прошло - без ожидания"
