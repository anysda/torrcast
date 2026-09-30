"""Проверяет планировщик приговоров полок: порядок одной руки, ширина, закрытие и двойники."""

from __future__ import annotations

import threading

from web.shelf_judge import Verdict, shelf_judge


def _lane(*keys: str) -> list[tuple[str, str]]:
    return [(f"q-{key}", key) for key in keys]


def test_one_hand_asks_exactly_what_the_serial_cut_asked() -> None:
    """Одна рука: «не играет» уступает место следующему, и после набора лимита - ни шагу."""
    asked: list[str] = []
    closed: list[int] = []
    verdicts: dict[str, Verdict] = {}

    def playable(_query: str, key: str) -> Verdict:
        asked.append(key)
        return key != "b"

    shelf_judge(
        lambda: [_lane("a", "b", "c", "d")], 2, playable, 1, closed.append, lambda: None, verdicts
    )

    assert asked == ["a", "b", "c"]
    assert closed == [0]
    assert verdicts == {"a": True, "b": False, "c": True}


def test_an_unknown_verdict_keeps_its_place_like_a_yes() -> None:
    """«Не знаю» не приговор: место не освобождается, и следующий кандидат не спрашивается."""
    asked: list[str] = []

    def playable(_query: str, key: str) -> Verdict:
        asked.append(key)
        return None

    shelf_judge(lambda: [_lane("a", "b", "c")], 2, playable, 1, lambda _i: None, lambda: None, {})

    assert asked == ["a", "b"]


def test_several_hands_judge_at_the_same_time() -> None:
    """Три руки - три приговора разом: барьер на троих рухнул бы при очереди по одному."""
    together = threading.Barrier(3, timeout=5.0)

    def playable(_query: str, _key: str) -> Verdict:
        together.wait()
        return True

    verdicts: dict[str, Verdict] = {}
    shelf_judge(
        lambda: [_lane("a", "b", "c")], 3, playable, 3, lambda _i: None, lambda: None, verdicts
    )

    assert verdicts == {"a": True, "b": True, "c": True}


def test_a_finished_shelf_closes_while_the_other_is_still_judged() -> None:
    """Готовые «Новинки» не ждут последнего приговора «Популярного»."""
    fresh_closed = threading.Event()
    order: list[str] = []

    def playable(_query: str, key: str) -> Verdict:
        if key == "slow":
            order.append("slow waits" if fresh_closed.wait(5.0) else "slow timed out")
        return True

    def closed(index: int) -> None:
        order.append(f"closed {index}")
        if index == 0:
            fresh_closed.set()

    shelf_judge(lambda: [_lane("a"), _lane("slow")], 1, playable, 2, closed, lambda: None, {})

    assert order == ["closed 0", "slow waits", "closed 1"]


def test_a_picture_on_both_shelves_is_judged_once() -> None:
    """Одна картина на двух полках - один поход в TorrServer, приговор обеим."""
    asked: list[str] = []

    def playable(_query: str, key: str) -> Verdict:
        asked.append(key)
        return True

    verdicts: dict[str, Verdict] = {}
    lanes = [_lane("a", "b"), _lane("b", "a")]
    shelf_judge(lambda: lanes, 2, playable, 2, lambda _i: None, lambda: None, verdicts)

    assert sorted(asked) == ["a", "b"]
    assert verdicts == {"a": True, "b": True}


def test_a_lane_whose_covers_are_still_landing_is_not_closed_short() -> None:
    """Пока обложки едут, дошедшая до конца очередь ждёт прибавки, а не закрывается."""
    lane = _lane("a")
    closed: list[int] = []
    ticks: list[int] = []
    verdicts: dict[str, Verdict] = {}

    def tick() -> None:
        ticks.append(1)
        if len(ticks) == 2:
            lane.extend(_lane("b"))

    shelf_judge(
        lambda: [list(lane)],
        2,
        lambda _query, _key: True,
        1,
        closed.append,
        tick,
        verdicts,
        lambda: len(ticks) < 3,
    )

    assert closed == [0]
    assert verdicts == {"a": True, "b": True}
