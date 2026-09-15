"""Поиск на главной как поведение: настоящие ``home.js`` и ``tile.js`` в node без браузера.

Сценарии и страница без браузера лежат в ``tests/web_js``: время там виртуальное, сервер
отвечает по сценарию, а сюда приезжают только факты экрана. Node - такой же инструмент
гейта, как ffmpeg: без него проверка краснеет, а не пропускается.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "search.js"
#: Шаги опроса из договора выдачи: пока показать нечего и когда уже есть что.
EMPTY_STEP_MS, HITS_STEP_MS = 150, 400
#: Сверх срока сервера страница ждёт не больше этого: опрос перед сроком и его дорога.
PAST_DEADLINE_MS = 3000
#: Шаг дозапроса обложек после финала, пока сервер говорит, что они в пути.
POSTER_STEP_MS = 2500


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail(
            "node не найден: сторожа поиска на главной исполняют home.js в node, поставь nodejs",
            pytrace=False,
        )
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=120, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def _scenario(facts: dict[str, Any], name: str) -> dict[str, Any]:
    one: dict[str, Any] = facts[name]
    assert "crashed" not in one, one.get("crashed")
    assert one["errors"] == [], f"страница упала посреди опроса: {one['errors']}"
    return one


@pytest.mark.machine
def test_polling_without_a_final_stops_at_the_server_deadline(facts: dict[str, Any]) -> None:
    endless = _scenario(facts, "endless")
    deadline = endless["finalBy"] * 1000
    assert endless["polls"][-1] >= deadline, "страница бросила опрос раньше срока сервера"
    assert endless["polls"][-1] <= deadline + PAST_DEADLINE_MS, (
        f"опрос шёл до {endless['polls'][-1]} мс при сроке сервера {deadline} мс"
    )
    assert endless["timers"] == 0, "после срока у страницы остались живые таймеры опроса"


@pytest.mark.machine
def test_a_final_late_within_the_server_deadline_is_drawn_with_best_match(
    facts: dict[str, Any],
) -> None:
    late = _scenario(facts, "late")
    assert late["screen"]["best"] == 1, "финал на 18 с при сроке 20 с не встал на экран"
    assert late["screen"]["searching"] == 0


@pytest.mark.machine
def test_poll_steps_are_short_before_hits_long_after_and_one_after_the_final(
    facts: dict[str, Any],
) -> None:
    steps = _scenario(facts, "steps")
    polls, latency = steps["polls"], steps["latency"]
    gaps = [later - earlier for earlier, later in pairwise(polls)]
    expected = [latency + EMPTY_STEP_MS] * 3 + [latency + HITS_STEP_MS] * 3
    assert gaps == expected, gaps
    assert steps["timers"] == 0, "финал без обложек в пути оставил живой таймер"


@pytest.mark.machine
def test_a_final_equal_to_the_last_preview_still_shows_best_match(facts: dict[str, Any]) -> None:
    equal = _scenario(facts, "equal")
    # Два превью и финал; дозапроса нет: сервер не сказал, что обложки в пути.
    assert equal["polls"] == 3
    assert equal["screen"]["best"] == 1, "финал, равный превью, не перерисован: нет Best match"
    assert equal["screen"]["searching"] == 0, "строка «ищем» осталась над финалом"


@pytest.mark.machine
def test_a_poster_finished_after_the_final_reaches_its_tile(facts: dict[str, Any]) -> None:
    after = _scenario(facts, "posterAfterFinal")
    gaps = [later - earlier for earlier, later in pairwise(after["polls"])]
    assert gaps == [POSTER_STEP_MS + 30] * 2, "дозапрос шёл не шагом или после «обложки пришли»"
    assert after["screen"]["keys"] == ["cars"]
    assert "web.tile.no_art" not in after["screen"]["text"], "готовая обложка не заменила заглушку"
    assert after["timers"] == 0, "дозапрос обложек стал бесконечным опросом"


@pytest.mark.machine
def test_posters_said_to_be_coming_forever_stop_at_the_server_cap(facts: dict[str, Any]) -> None:
    cap = _scenario(facts, "posterCap")
    assert cap["polls"][-1] <= cap["postersBy"] * 1000, f"дозапрос шёл до {cap['polls'][-1]} мс"
    assert len(cap["polls"]) == 1 + (cap["postersBy"] * 1000 - 30) // (POSTER_STEP_MS + 30)
    assert cap["timers"] == 0, "после потолка у страницы остались живые таймеры"


@pytest.mark.machine
def test_the_poster_cap_counts_from_the_final_answer(facts: dict[str, Any]) -> None:
    """Сервер называет секунды до своего потолка: страница считает их от ответа, не от начала.

    Заход сервера бывает старше страницы, и опрос за его потолком гнал новый круг поиска."""
    cap = _scenario(facts, "posterCapFromFinal")
    assert cap["polls"][-1] <= cap["capAt"], f"дозапрос шёл за потолком сервера: {cap['polls']}"
    assert cap["polls"][-1] > cap["capAt"] - 2 * POSTER_STEP_MS, (
        f"дозапрос бросили задолго до потолка сервера: {cap['polls']}"
    )
    assert cap["timers"] == 0


@pytest.mark.machine
def test_a_poll_held_past_the_deadline_still_gets_the_final(facts: dict[str, Any]) -> None:
    """🔴 TC-1286: опрос, начатый до срока и застрявший за ним, обрывал поиск без финала."""
    held = _scenario(facts, "held")
    assert held["screen"]["best"] == 1 and held["screen"]["searching"] == 0
    assert held["screen"]["failed"] == 0


@pytest.mark.machine
def test_one_failed_poll_of_a_live_search_is_not_a_failure(facts: dict[str, Any]) -> None:
    blip = _scenario(facts, "blip")
    assert blip["screen"]["failed"] == 0, "живой поиск объявил сбой на одном сорванном опросе"
    assert blip["screen"]["best"] == 1


@pytest.mark.machine
def test_a_lost_search_keeps_its_tiles_and_try_again_focuses_the_first(
    facts: dict[str, Any],
) -> None:
    lost = _scenario(facts, "lost")
    assert lost["failed"]["failed"] == 1
    assert lost["failed"]["keys"] == ["k0", "k1", "k2"], "сбой стёр показанные плитки"
    assert lost["after"]["failed"] == 0 and lost["after"]["best"] == 1
    assert lost["after"]["focus"] == "k0", f"фокус после повтора: {lost['after']['focus']}"
    assert lost["timers"] == 0


@pytest.mark.machine
@pytest.mark.parametrize("name", ["failedNetwork", "failedServer"])
def test_a_failed_search_never_draws_the_empty_result(facts: dict[str, Any], name: str) -> None:
    failed = _scenario(facts, name)
    assert failed["screen"]["failed"] == 1
    assert failed["screen"]["failedKeys"] == 1, "повтор не достать стрелками пульта"
    assert "web.search.failed" in failed["screen"]["text"]
    assert "web.search.empty" not in failed["screen"]["text"]


@pytest.mark.machine
def test_a_failed_search_retries_the_same_query(facts: dict[str, Any]) -> None:
    retried = _scenario(facts, "retry")
    assert retried["queries"] == ["тачки", "тачки"]
    assert retried["screen"]["failed"] == 0


@pytest.mark.machine
def test_a_catalog_tile_without_releases_dims_and_does_not_open(facts: dict[str, Any]) -> None:
    dim = _scenario(facts, "dim")
    assert (dim["during"]["waiting"], dim["during"]["dim"]) == (1, 0)
    assert (dim["after"]["waiting"], dim["after"]["dim"]) == (0, 1)
    assert dim["opened"] == ["a"], "погасшая плитка открывает карточку"


@pytest.mark.machine
def test_focus_on_the_second_row_stays_on_its_picture(facts: dict[str, Any]) -> None:
    second = _scenario(facts, "second")
    assert (second["before"], second["added"], second["after"]["focus"]) == ("k8", "k8", "k8")


@pytest.mark.machine
def test_focus_follows_a_hit_that_landed_in_a_catalog_tile(facts: dict[str, Any]) -> None:
    slot = _scenario(facts, "slot")
    assert slot["before"] == "k"
    assert slot["after"]["focus"] == "k", f"фокус ушёл на {slot['after']['focus']}"
