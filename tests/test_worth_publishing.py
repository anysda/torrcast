"""Публикация нового тела полок: без предшественника - да, иначе - усушка и мусор."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE
from web.drop_count import DropCount
from web.worth_publishing import MASS_DROP, worth_publishing


def _body(count: int, rule: int = RULE) -> dict[str, JsonValue]:
    tiles: list[JsonValue] = [{"title": f"Картина {index:02d}"} for index in range(count)]
    return {FIELD: rule, "fresh": tiles, "popular": list(tiles), "built_at": None}


def _drops(checked: int, dropped: int) -> DropCount:
    return DropCount(checked=checked, dropped=dropped)


def test_a_cold_start_publishes_even_an_empty_body() -> None:
    """Без диска и без прежней сборки правила защищать нечего - первый заход идёт как есть."""
    current: dict[str, JsonValue] = {FIELD: RULE, "fresh": [], "popular": [], "built_at": None}

    assert worth_publishing(current, _body(0), _drops(0, 0)) is True


def test_a_body_from_another_rule_does_not_block_a_short_build() -> None:
    """Прежнее тело другого правила отбора - не предшественник, планка его не читает."""
    current = _body(25, rule=RULE - 1)

    assert worth_publishing(current, _body(10), _drops(10, 0)) is True


def test_a_drastic_shrink_is_blocked() -> None:
    """Новая полка меньше половины прежней - публикация отступает."""
    current = _body(25)

    assert worth_publishing(current, _body(10), _drops(10, 0)) is False


def test_a_moderate_shrink_is_allowed() -> None:
    """Не половина, а честный небольшой отсев - публикуется, планка тут не про 20."""
    current = _body(25)

    assert worth_publishing(current, _body(18), _drops(18, 0)) is True


def test_the_shrink_boundary_is_exact() -> None:
    """Ровно на планке (половина) публикация ещё проходит - меньше половины уже нет."""
    current = _body(20)

    assert worth_publishing(current, _body(10), _drops(10, 0)) is True
    assert worth_publishing(current, _body(9), _drops(9, 0)) is False


def test_an_empty_new_body_never_replaces_a_live_one() -> None:
    """Пустая новая полка при непустой прежней попадает под ту же усушку, без отдельного правила."""
    current = _body(25)

    assert worth_publishing(current, _body(0), _drops(0, 0)) is False


def test_a_mass_drop_ratio_blocks_publishing() -> None:
    """Доля честных «не играет» выше нормы - заход подозрителен, публикация отступает."""
    current = _body(25)
    dropped = int(MASS_DROP * 100) + 5

    assert worth_publishing(current, _body(25), _drops(100, dropped)) is False


def test_a_normal_drop_ratio_publishes() -> None:
    """Доля в пределах нормы (замер живого стенда ~21%) не мешает публикации."""
    current = _body(25)
    dropped = int(MASS_DROP * 100) - 5

    assert worth_publishing(current, _body(25), _drops(100, dropped)) is True


def test_unknown_verdicts_do_not_count_toward_the_mass_drop_guard() -> None:
    """«Не знаю» раздуло бы знаменатель зря - доля считается по узнанным (см. DropCount.ratio)."""
    current = _body(25)
    drops = DropCount(checked=100, dropped=10, unknown=80)  # 10/20 подтверждённых = 50%

    assert worth_publishing(current, _body(25), drops) is False
