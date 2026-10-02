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
#: Окно общего прихода обложек от начала поиска, мс. Раньше 3 с пачка уходила бы без обложек,
#: что ложатся на 2-3 с (медиана прихода 2.95 с); позже 4 с она снова стала бы ожиданием
#: (стенд 02-10-2026, 45 заходов).
COVERS_FROM_MS, COVERS_UNTIL_MS = 3000, 4000
#: Сверх срока сервера страница ждёт не больше этого: опрос перед сроком и его дорога.
PAST_DEADLINE_MS = 3000
# Запас страницы до потолка обложек сервера (``TCHome._CAP_MARGIN``).
CAP_MARGIN_MS = 1000


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
def test_a_final_answer_polls_for_posters_without_replacing_its_tiles(
    facts: dict[str, Any],
) -> None:
    after = _scenario(facts, "posterAfterFinal")
    assert len(after["polls"]) == 3, after["polls"]
    assert after["swaps"] == 1, "поздняя обложка пересобрала весь #tc-body"
    assert after["screen"]["keys"] == ["cars"]
    assert "web.tile.no_art" not in after["screen"]["text"], "поздняя обложка не встала в плитку"
    assert after["timers"] == 0, "после финала остался таймер дозапроса обложек"


@pytest.mark.machine
def test_a_first_row_held_for_its_covers_keeps_the_skeleton_and_is_drawn_once(
    facts: dict[str, Any],
) -> None:
    held = _scenario(facts, "heldFirstRow")
    assert held["polls"] == 6, held["polls"]
    assert held["swaps"] == 1, "пустой придержанный ответ пересобрал скелет поиска"
    assert held["screen"]["keys"] == ["cars"]
    assert held["screen"]["best"] == 1


@pytest.mark.machine
def test_posters_said_to_be_coming_forever_stop_at_the_server_cap(facts: dict[str, Any]) -> None:
    cap = _scenario(facts, "posterCap")
    assert cap["polls"][-1] <= cap["postersBy"] * 1000, f"дозапрос шёл до {cap['polls'][-1]} мс"
    assert cap["polls"][-1] > cap["postersBy"] * 1000 - 2 * CAP_MARGIN_MS, (
        f"дозапрос бросили задолго до потолка сервера: {cap['polls']}"
    )
    assert cap["timers"] == 0, "после потолка у страницы остались живые таймеры"


@pytest.mark.machine
def test_the_poster_cap_counts_from_the_final_answer(facts: dict[str, Any]) -> None:
    """Сервер называет секунды до своего потолка: страница считает их от ответа, не от начала.

    Заход сервера бывает старше страницы, и опрос за его потолком гнал новый круг поиска."""
    cap = _scenario(facts, "posterCapFromFinal")
    assert cap["polls"][-1] <= cap["capAt"], f"дозапрос шёл за потолком сервера: {cap['polls']}"
    assert cap["polls"][-1] > cap["capAt"] - 2 * CAP_MARGIN_MS, (
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
@pytest.mark.parametrize("end", ["network", "server", "refused", "empty"])
def test_a_held_first_row_skeleton_gives_way_to_how_the_search_ended(
    facts: dict[str, Any], end: str
) -> None:
    held = _scenario(facts, "heldThenEnd")
    ended = held[end]
    assert ended["polls"] >= 4, ended["polls"]
    assert ended["skeletons"] == 0, "скелет придержанного ряда остался на экране"
    assert ended["screen"]["searching"] == 0, "строка «Ищем…» осталась после конца поиска"
    assert ended["timers"] == 0, "после конца поиска у страницы остались таймеры опроса"
    text = ended["screen"]["text"]
    if end in ("network", "server"):
        assert ended["screen"]["failed"] == 1
        assert "web.search.failed" in text
    elif end == "refused":
        assert held["reason"]["key"] in text
        assert ended["screen"]["failed"] == 0
    else:
        assert "web.search.empty" in text


@pytest.mark.machine
@pytest.mark.parametrize("name", ["failedNetwork", "failedServer"])
def test_a_failed_search_never_draws_the_empty_result(facts: dict[str, Any], name: str) -> None:
    failed = _scenario(facts, name)
    assert failed["screen"]["failed"] == 1
    assert failed["screen"]["failedKeys"] == 1, "повтор не достать стрелками пульта"
    assert "web.search.failed" in failed["screen"]["text"]
    assert "web.search.empty" not in failed["screen"]["text"]


@pytest.mark.machine
def test_a_named_refusal_is_read_on_the_screen_and_not_offered_a_retry(
    facts: dict[str, Any],
) -> None:
    """The named key and values reach the screen without offering a retry."""
    refused = _scenario(facts, "refused")

    assert refused["reason"]["key"] in refused["screen"]["text"]
    assert refused["screen"]["failed"] == 0, "отказу по существу предложили «повторить»"
    assert "web.search.failed" not in refused["screen"]["text"]
    assert len(refused["polls"]) == 1, "после отказа страница пошла опрашивать дальше"


@pytest.mark.machine
def test_a_named_refusal_after_the_deadline_replaces_the_empty_snapshot(
    facts: dict[str, Any],
) -> None:
    late = _scenario(facts, "lateRefusal")

    assert late["reason"]["key"] in late["screen"]["text"]
    assert late["screen"]["text"] == late["reason"]["key"] + "web.search.empty_hint"
    assert late["screen"]["failed"] == 0
    assert len(late["polls"]) == 3, "финал без флага всё ещё опрашивался или отказ не дослушали"
    assert late["timers"] == 0


@pytest.mark.machine
@pytest.mark.parametrize("name", ["cutEmpty", "lateFailed"])
def test_a_cut_empty_circle_is_a_failed_search_with_a_retry(
    facts: dict[str, Any], name: str
) -> None:
    """A circle that missed indexers never reads as «nothing found» or as a named reason."""
    cut = _scenario(facts, name)
    assert cut["screen"]["text"].startswith("web.search.failed")
    assert "web.search.empty" not in cut["screen"]["text"]
    assert cut["screen"]["failedKeys"] == 1, "сбойный круг не предложил повтор"


@pytest.mark.machine
def test_returning_to_a_failed_search_asks_again(facts: dict[str, Any]) -> None:
    """Its empty deadline list is not an answer, so it never comes back as «nothing found»."""
    late = _scenario(facts, "lateFailed")
    assert late["askedAgain"] == 1
    assert "web.search.empty" not in late["returned"]["text"]


@pytest.mark.machine
def test_a_torn_poll_does_not_end_listening_to_a_late_circle(facts: dict[str, Any]) -> None:
    torn = _scenario(facts, "tornListen")
    assert torn["screen"]["text"] == torn["reason"]["key"] + "web.search.empty_hint"
    assert torn["screen"]["failed"] == 0
    assert torn["timers"] == 0


@pytest.mark.machine
def test_every_named_search_refusal_keeps_its_own_page_key(facts: dict[str, Any]) -> None:
    refused = _scenario(facts, "namedRefusals")

    assert [screen["text"] for screen in refused["screens"]] == [
        reason["key"] + "web.search.empty_hint" for reason in refused["reasons"]
    ]
    assert all(screen["failed"] == 0 for screen in refused["screens"])
    assert all("web.search.failed" not in screen["text"] for screen in refused["screens"])


@pytest.mark.machine
def test_a_named_refusal_survives_returning_to_its_preview(facts: dict[str, Any]) -> None:
    returned = _scenario(facts, "returnAfterRefusal")

    for screen in (returned["refusal"], returned["returned"]):
        assert returned["reason"]["key"] in screen["text"]
        assert screen["best"] == 0


@pytest.mark.machine
def test_a_failed_search_retries_the_same_query(facts: dict[str, Any]) -> None:
    retried = _scenario(facts, "retry")
    assert retried["queries"] == ["тачки", "тачки"]
    assert retried["screen"]["failed"] == 0


@pytest.mark.machine
def test_a_catalog_tile_without_releases_waits_and_then_opens_by_its_own_name(
    facts: dict[str, Any],
) -> None:
    """🔴 TC-1312. Экран гасил и лишал клика картины, которые на самом деле играются.

    Круг спрошен по набранному тексту, и его молчание о картине - не приговор ей: «Атаки
    клонов» по строке «star wars» круг не принёс, а по её собственному имени принёс 57
    раздач. Поэтому ждёт плитка только пока круг идёт, гасить нечего вовсе, клик остаётся
    у всех, а карточка плитки без находки спрашивает раздачи по имени своей картины.
    Находка круга (``pick``) остаётся на набранном тексте: её раздачи уже сосчитаны, и
    платить за них второй раз нечем. Греется экран по-прежнему одним кругом набранного
    текста: иначе каждая плитка ставила бы в очередь свой круг к тем же индексерам.
    """
    waiting = _scenario(facts, "waiting")
    assert (waiting["during"]["waiting"], waiting["during"]["dim"]) == (1, 0)
    assert (waiting["after"]["waiting"], waiting["after"]["dim"]) == (0, 0)
    assert waiting["opened"] == ["a", "c"], "плитка без раздач потеряла клик"
    assert waiting["cards"] == [["a", "тачки"], ["c", "T c"]], "карточку просят не тем именем"
    assert waiting["warm"] == ["тачки", "тачки"], "прогрев экрана стоит круга на каждую плитку"


@pytest.mark.machine
def test_focus_on_the_second_row_stays_on_its_picture(facts: dict[str, Any]) -> None:
    second = _scenario(facts, "second")
    assert (second["before"], second["added"], second["after"]["focus"]) == ("k8", "k8", "k8")


@pytest.mark.machine
def test_focus_follows_a_hit_that_landed_in_a_catalog_tile(facts: dict[str, Any]) -> None:
    slot = _scenario(facts, "slot")
    assert slot["before"] == "k"
    assert slot["after"]["focus"] == "k", f"фокус ушёл на {slot['after']['focus']}"


def test_late_covers_of_standing_tiles_land_in_one_arrival(facts: dict[str, Any]) -> None:
    """Обложки, пришедшие на разных опросах, встают за один проход, а не плитка за плиткой."""
    once = _scenario(facts, "coversOnce")
    painted = once["painted"]
    assert sorted(one["key"] for one in painted) == ["a", "b"], painted
    assert len({one["at"] for one in painted}) == 1, f"обложки встали рывками: {painted}"
    assert once["noArt"] == [], "обложка не встала в плитку"
    assert once["timers"] == 0


def test_the_cover_arrival_leaves_at_its_deadline_and_late_ones_stay_placeholders(
    facts: dict[str, Any],
) -> None:
    """Непришедшая обложка не держит пачку дольше срока; опоздавшая к пачке не встаёт кадром."""
    late = _scenario(facts, "coversDeadline")
    painted = late["painted"]
    assert [one["key"] for one in painted] == ["b"], painted
    assert COVERS_FROM_MS <= painted[0]["at"] <= COVERS_UNTIL_MS, f"пачка вне окна: {painted}"
    assert late["noArt"] == ["a"], "плитка без обложки к пачке получила её отдельным кадром"
    assert late["screen"]["keys"] == ["a", "b"]
