"""Зеркало :mod:`torrcast.domain.start_settings`: сроки старта, паузы и голоса показа.

Сторожится порядок сроков между собой: короткая пауза не может быть длиннее долгой, а
показ обязан успеть сказать про таймлайн раньше, чем пауза погасит упаковку.
"""

from __future__ import annotations

from torrcast.domain.hls_wait import KEYS_WAIT, PILOT_TIMEOUT
from torrcast.domain.start_settings import (
    FIRST_FRAME_POLL,
    PAUSE_LIMIT,
    PAUSE_SECONDS,
    SAY_SECONDS,
    START_SLACK,
)
from torrcast.domain.start_timeout import START_TIMEOUT
from torrcast.domain.worker_settings import WORKER_DUR, WORKER_META

#: Как часто показ опрашивает приёмник: на этом такте и держится всё, что он говорит.
POLL_SECONDS = 2.0


def test_the_first_frame_poll_is_tighter_than_the_usual_one() -> None:
    """До первого кадра приёмник спрашивается чаще обычного такта, иначе учащение бессмысленно.

    Флажок «картинка» ставится только на круге опроса, поэтому шаг опроса - это и есть
    запас вранья строки «старт NN с»: при обычном шаге она запаздывала за настоящим
    кадром на 1.9-3.8 с. Выровняй срока - и строка снова отстанет на весь такт.
    """
    assert 0 < FIRST_FRAME_POLL < POLL_SECONDS


def test_the_short_pause_is_shorter_than_the_one_that_ends_the_show() -> None:
    """Пауза на пульте и пауза, кончающая показ, - разные сроки, и порядок у них один.

    Первая гасит упаковку (иначе сегменты копились бы в tmpfs впустую), вторая гасит юнит
    целиком. Поменяй их местами - и показ кончался бы раньше, чем переставал паковать, то
    есть человек терял бы сеанс на обычной паузе.
    """
    assert PAUSE_SECONDS < PAUSE_LIMIT


def test_the_show_speaks_about_the_timeline_before_a_pause_can_stop_the_packing() -> None:
    """Строка про позицию и общее время обязана успеть выйти хотя бы раз до гашения упаковки.

    Эта строка - единственное доказательство того, что на экране есть таймлайн. Скажи её
    реже, чем терпится пауза, - и о паузе в журнале осталась бы только сама пауза, без
    единой отметки о том, что до неё показывали.
    """
    assert SAY_SECONDS < PAUSE_SECONDS


def test_the_show_speaks_on_a_throttle_and_not_on_every_single_poll() -> None:
    """Строка про таймлайн выходит РЕЖЕ опроса: это придержка, а не эхо опроса.

    Приёмник опрашивается раз в две секунды (:data:`TRACE_ENV` объясняет это прямым
    текстом). Сравняй срок с опросом или опусти ниже - и придержки не осталось бы вовсе:
    журнал заполнился бы той самой строкой, ради разрежения которой срок и заведён, а
    редкие важные записи утонули бы среди неё.
    """
    assert SAY_SECONDS > POLL_SECONDS


def test_the_slack_is_counted_as_a_real_cost_but_never_as_a_phase_of_its_own() -> None:
    """Прочее на пути до картинки стоит секунд, и считать их нулём - врать себе.

    Но это именно остаток: запуск юнита, чтение состояния, подъём раздачи. Стань он вровень
    с настоящими фазами - бюджет старта перестал бы быть суммой замеренных потолков и стал
    бы числом с запасом.
    """
    assert START_SLACK > 0
    assert min(WORKER_META, WORKER_DUR, KEYS_WAIT, PILOT_TIMEOUT, START_TIMEOUT) > START_SLACK
