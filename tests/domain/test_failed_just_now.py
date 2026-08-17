"""Проверяет, что отказом этого поиска считается только отказ на наших глазах."""

import time
from datetime import UTC, datetime, timedelta

from torrcast.domain.failed_just_now import CLOCK_SLACK, failed_just_now
from torrcast.domain.failure_moment import failure_moment


def _ago(seconds: float) -> str:
    """Время отказа глазами Prowlarr: UTC с ``Z`` на конце, как на живом стенде."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_отказ_после_начала_поиска_считается_нашим() -> None:
    assert failed_just_now(_ago(0), time.time())


def test_вчерашний_отказ_сегодняшнюю_пустоту_не_объясняет() -> None:
    """Источник мог отказать час назад и с тех пор ожить - иначе первая же старая
    отметка навсегда отменила бы честное «ничего не нашлось»."""
    assert not failed_just_now(_ago(3600), time.time())


def test_непрочитанное_время_никого_не_обвиняет() -> None:
    """Ошибиться сюда дёшево, а в другую сторону - дорого: это честная пустая полка,
    объявленная отказом канала."""
    assert not failed_just_now("не время вовсе", time.time())


def test_припуск_покрывает_отрезанные_доли_секунды() -> None:
    """Отметку ставит Prowlarr, а не наш секундомер, и доли секунды мы отрезаем сами.

    Отсчёт ведём от самой отметки, а не от стенных часов: припуск тут и меряется.
    """
    stamp = "2026-08-09T20:13:28Z"
    moment = failure_moment(stamp)
    assert moment is not None
    assert failed_just_now(stamp, moment + CLOCK_SLACK), "отметка чуть раньше начала - наша"
    assert not failed_just_now(stamp, moment + CLOCK_SLACK + 1), "за припуском - чужая"
