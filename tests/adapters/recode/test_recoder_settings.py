"""Длина одного захода кодировщика: ограничение по отзывчивости, а не по мощности."""

from __future__ import annotations

from torrcast.adapters.recode.recoder_settings import RUN_MAX
from torrcast.adapters.recode.recoder_state import _State


def test_a_run_stays_short_enough_to_be_dropped_on_a_seek() -> None:
    """Бросить можно только заход целиком, поэтому длинный заход - это долгая перемотка."""
    assert RUN_MAX == 6


def test_the_recoder_takes_this_number_as_its_own_default() -> None:
    """Умолчание поля и есть та же величина: второго источника правды тут быть не должно."""
    assert _State.__dataclass_fields__["run_max"].default == RUN_MAX
