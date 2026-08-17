"""Пороги приёмника умолчанием: все они - осторожный профиль, и ни один не выдуман."""

from __future__ import annotations

from torrcast.adapters.chromecast.cast.receiver_settings import _Settings
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.start_timeout import START_TIMEOUT


def test_every_threshold_that_belongs_to_a_profile_comes_from_the_cautious_one() -> None:
    """Числа сторожа не прибиты здесь: они приходят из профиля приёмника.

    Разъедься умолчание с профилем - и приёмник без выбранного профиля вёл бы себя
    иначе, чем тот же приёмник с осторожным профилем, а различить это было бы нечем.
    """
    assert _Settings.START_TIMEOUT is START_TIMEOUT
    assert CAUTIOUS.revive_timeout == _Settings.REVIVE_TIMEOUT
    assert CAUTIOUS.load_retries == _Settings.LOAD_RETRIES
    assert CAUTIOUS.stall_seconds == _Settings.STALL_SECONDS
    assert CAUTIOUS.ready_ahead == _Settings.READY_AHEAD
    assert CAUTIOUS.stall_skip == _Settings.STALL_SKIP
    assert CAUTIOUS.blind_nudges == _Settings.BLIND_NUDGES


def test_the_app_ids_are_the_ones_the_receiver_actually_reports() -> None:
    """Default Media Receiver и заставка: по ним отличается наш показ от пустого экрана."""
    assert _Settings.MEDIA_APP == "CC1AD845"
    assert _Settings.BACKDROP_APP == "E8C28D3C"


def test_the_watchdog_thresholds_keep_the_order_that_makes_them_work() -> None:
    """Порог перемотки назад больше шага нуджа, а прыжок перемотки больше хода показа.

    Стань откат меньше шага нуджа - свой же прыжок вперёд считался бы перемоткой
    человека; стань порог прыжка меньше хода показа за опрос - перемоткой считался бы
    обычный ход фильма.
    """
    assert _Settings.REWIND == 8.0, "больше сегмента брать нельзя: откат на кусок - обычное дело"
    assert _Settings.REWIND >= _Settings.STALL_SKIP
    assert _Settings.SEEK_JUMP > _Settings.REWIND
    assert _Settings.PICTURE_STEP < 2.0, "меньше шага показа за опрос (2 с)"
    assert _Settings.CUT_SLACK > 0.0, "ноль вернул бы прыжок в тот же кусок"


def test_a_dead_segment_needs_more_than_one_death_to_be_stepped_over() -> None:
    """Моргнувшая сеть тоже гасит показ: первая смерть о куске ещё ничего не говорит."""
    assert _Settings.DEADLY_TRIES == 3


def test_the_wake_budget_is_shorter_than_the_revive_one() -> None:
    """Одна попытка подъёма не имеет права висеть пять минут: интервалы держит зовущий.

    Провиси она столько - показ проспал бы вернувшуюся сеть. Минуты хватает с запасом:
    живой Q70D отвечает PLAYING за 0.7-1.5 с.
    """
    assert _Settings.WAKE_TIMEOUT == 60.0
    assert _Settings.WAKE_TIMEOUT < _Settings.REVIVE_TIMEOUT


def test_the_numbers_of_the_load_retry_are_the_measured_ones() -> None:
    """Пауза перед повтором и терпение к молчаливому IDLE - замеры, а не круглые числа.

    Живой Q70D отвечает PLAYING за 0.7-1.5 с, и 30 с молчания означают, что грузить он
    не начинал; ресиверу при этом нужно время закрыть прошлую сессию - отсюда пауза.
    """
    assert _Settings.LOAD_PAUSE == 3.0
    assert _Settings.STUCK_SECONDS == 30.0
    assert _Settings.STUCK_SECONDS > _Settings.LOAD_PAUSE, "иначе отказ не отличить от паузы"
