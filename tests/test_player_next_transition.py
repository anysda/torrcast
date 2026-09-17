"""Сторож перехода между сериями (TC-1336) как поведение, не как грепанье строк.

Мержер прогнал шесть отрицательных проб по прежнему, греповому виду этого файла - все
семь его тестов остались зелёными на каждой из них, плюс не заметили дефект фильма
(ранний уход за 10 с до конца картины). Греп держит присутствие строк, а не поведение.

Тут - настоящие ``player.js``/``player-box.js``/``player-next.js``/``player-panel.js``/
``player-screens.js`` в node без браузера (``tests/web_js/player_page.js``, тем же
приёмом, что и у поиска на главной: ``tests/web_js/page.js`` + ``tests/test_home_search_
js.py``), время виртуальное, сервер отвечает по сценарию. Сценарии и таблица «поломка -
какой тест упал» - в ``results-a.md`` полосы A.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

RUNNER = Path(__file__).resolve().parent / "web_js" / "player.js"


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.fail(
            "node не найден: сторож перехода исполняет player.js в node, поставь nodejs",
            pytrace=False,
        )
    done = subprocess.run(
        [node, str(RUNNER)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    said: dict[str, Any] = json.loads(done.stdout)
    return said


def _scenario(facts: dict[str, Any], name: str) -> dict[str, Any]:
    one: dict[str, Any] = facts[name]
    assert "crashed" not in one, one.get("crashed")
    assert one["errors"] == [], f"сценарий упал посреди прогона: {one['errors']}"
    return one


@pytest.mark.machine
def test_the_countdown_appears_at_the_promised_threshold_and_not_earlier(
    facts: dict[str, Any],
) -> None:
    """Плашка встаёт на 10-й секунде обещания, а не на старой зашитой 1-й.

    До правки лишний порог ``<= 1`` держал бы её немой при 5.5 с остатка - именно это
    ловит отрицательная проба (б) («дописать вторым условием ``<= 1.0``»).
    """
    said = _scenario(facts, "seriesCountdown")
    assert said["beforeThreshold"] is False, "плашка встала раньше своих 10 секунд"
    assert said["atThreshold"] is True, "плашка не встала на 5.5 с остатка (порог 10)"


@pytest.mark.machine
def test_the_countdown_expires_naturally_removes_its_card_and_calls_next_once(
    facts: dict[str, Any],
) -> None:
    """Досчитала сама - карточка уходит из DOM и переход зовётся ровно один раз.

    Ловит пробу (д) («убрать ``TCApi.next(ended)`` из ветки без ящика» - перехода не
    было бы вовсе). Пробу (г) («убрать ``card.remove()`` из ``stop()``») в СБОРКЕ не
    ловит ничто - следующий же ``_playNext()``/``_cancelNext()`` сам заменяет весь
    оверлей (``overlay.replaceChildren()`` у любого экрана ``player-screens.js``), и
    дефект замаскирован; поэтому вторая половина этой проверки берёт ``player-next.js``
    в одиночку (``standaloneNextExpiry``, без остального плеера) - там рисовать после
    неё некому, карточка обязана снять себя сама.
    """
    said = _scenario(facts, "seriesCountdown")
    assert said["beforeExpiry"] is True, "карточка пропала до истечения счёта"
    assert said["afterExpiry"] is False, "карточка осталась в DOM после «0» (виснет)"
    assert said["nextCalls"] == 1, f"TCApi.next зовётся {said['nextCalls']} раз, не 1"
    assert said["nextArg"] == {"season": 1, "episode": 2}

    alone = _scenario(facts, "standaloneNextExpiry")
    assert alone["mounted"] is True
    assert alone["beforeExpiry"] is True, "карточка сама себя убрала до истечения счёта"
    assert alone["afterExpiry"] is False, "card.remove() не сработал - карточка виснет на «0»"
    assert alone["played"] == 1


@pytest.mark.machine
def test_a_stale_video_after_expiry_does_not_fire_a_second_transition(
    facts: dict[str, Any],
) -> None:
    """Старое видео, доигрывающее тот же хвост ПОСЛЕ перехода, второй раз не переводит.

    ``_ending`` обязан остаться true через всю ветку без готового ящика: иначе тот же
    ``timeupdate`` на ещё старой длительности зовёт ``_startNext`` второй раз."""
    said = _scenario(facts, "seriesCountdown")
    assert said["afterStaleTick"] is False, "карточка вернулась на доигрывающем видео"
    assert said["nextCalls"] == 1, "переход завёлся второй раз на том же хвосте"


@pytest.mark.machine
def test_cancel_removes_the_card_and_holds_off_the_transition(
    facts: dict[str, Any],
) -> None:
    """«Отмена» снимает карточку немедленно и не заводит переход даже потом.

    Регрессия мержера 17-09-2026: «Отмена» снимала и ``_ending`` - плашка возвращалась
    на «10» через четверть секунды после своей же «Отмена» на том же доигрывающем
    видео. Тут этот же хвост докармливается ПОСЛЕ клика - карточка обязана не вернуться.
    """
    said = _scenario(facts, "seriesCancelHolds")
    assert said["mounted"] is True
    assert said["goneRightAfter"] is True, "«Отмена» не убрала карточку из DOM"
    assert said["stillGone"] is True, "карточка вернулась на доигрывающем видео после «Отмена»"
    assert said["nextCalls"] == 0, "«Отмена» всё равно завела переход"


@pytest.mark.machine
def test_a_box_arriving_mid_countdown_is_deferred_not_torn_down(
    facts: dict[str, Any],
) -> None:
    """Ящик следующей серии, найденный ПОСРЕДИ счёта, не рвёт карточку на середине.

    Ловит пробы (а) («убрать ``_counting = true``») и (в) («инвертировать охрану
    ``if (!player._counting)`` в rebox») - под любой из них тот же ``rebox()`` тут же
    подменил бы кадр вместо того, чтобы придержать ящик."""
    said = _scenario(facts, "midCountdownReboxDefers")
    assert said["mountedBefore"] is True
    assert said["survivedPlayingBlip"] is True, "заминка-и-возобновление стёрла карточку"
    assert said["reboxResult"] is True, "rebox() не увидела новый ящик вовсе"
    assert said["survivedRebox"] is True, "новый ящик посреди счёта сорвал карточку"
    assert said["pendingKey"] == "k2", "новый ящик не лёг в _pendingBox"


@pytest.mark.machine
def test_the_deferred_box_opens_without_a_second_round_trip_and_calls_next_once(
    facts: dict[str, Any],
) -> None:
    """Досчитав, плашка открывает уже НАЙДЕННЫЙ ящик сама - не спрашивает его заново.

    Открытая серия обязана получить СВОЙ собственный автопереход: ``apply()``
    (`player-box.js`) обязан снять ``_ending`` синхронно, иначе новый ``timeupdate`` у
    следующей серии молчит навсегда под тем же условием ``!TCPlayer._ending``.
    """
    said = _scenario(facts, "midCountdownReboxDefers")
    assert said["afterExpiry"] is False, "карточка не убралась по истечении"
    assert said["appliedKey"] == "k2", "истечение счёта не открыло придержанный ящик"
    assert said["boxPolls"] == 2, (
        f"поход за ящиком случился {said['boxPolls']} раз - первый (посадка) и второй "
        "(находка посреди счёта); третьего быть не должно"
    )
    assert said["nextCalls"] == 1
    assert said["noCardMidway"] is False, "карточка новой серии встала посреди неё"
    assert said["secondCountdownAppears"] is True, (
        "открытая серия осталась без своего автоперехода - apply() не снял _ending"
    )


@pytest.mark.machine
def test_a_movie_does_not_leave_before_its_own_last_second(facts: dict[str, Any]) -> None:
    """Фильм и финал сезона (``has_next: false``) уходят у САМОГО конца, как на ``dev``.

    Владелец 17-09-2026: «плашка идёт поверх последних 10 секунд СЕРИИ», ранний выход
    из фильма в это не входит. До правки поднятый порог ``TCPlayerNext.SECONDS`` (10)
    стоял на ОБОИХ путях ``_startNext()`` - вкладка уезжала со страницы показа за 10 с
    до титров у каждого фильма и финала сезона (``hass/following.py``: ``None`` -
    фильм, последняя серия или тишина; ``hass/bridge.py:103`` кормит этим ``has_next``).
    """
    said = _scenario(facts, "movieDoesNotLeaveEarly")
    assert said["goneAt11"] == 0, "вкладка ушла за 11 с до конца фильма"
    assert said["goneAt9_5"] == 0, "вкладка ушла за 9.5 с до конца - это порог СЕРИИ, не фильма"
    assert said["cardAt9_5"] is False, "у фильма встала плашка перехода - переходить некуда"
    assert said["goneAt0_7"] == 1, "вкладка не ушла и на 0.7 с до конца (порог dev - 1 с)"
    assert said["path"] == "/"
