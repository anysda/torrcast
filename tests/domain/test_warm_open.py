"""Зеркало :mod:`torrcast.domain.warm_open`: сколько головы греем и что держим на полке.

Сторожатся связи, замеренные на живых файлах: голова под открытие входа меньше головы под
меню, mkv дешевле mp4, неизвестный контейнер берёт больший кусок, а таблица сдвига ``-ss``
описывает ровно те два контейнера, у которых есть карта опорных кадров.
"""

from __future__ import annotations

from torrcast.domain.hls_wait import KEYS_WAIT, PILOT_TIMEOUT
from torrcast.domain.warm_open import (
    HEAD_OPEN,
    HEAD_OPEN_DEFAULT,
    HEAD_WARM,
    KEYS_KEPT,
    KEYS_LOCK,
    PROBE_KEPT,
    SEEK_SHIFT,
    WARM_TIMEOUT,
)

#: Самый жирный замеренный ``moov`` mp4: без него ffmpeg вход не откроет вовсе.
FATTEST_MOOV_BYTES = 5_300_000

#: Средний вес карты опорных кадров на живой полке.
AVERAGE_KEYMAP_BYTES = 29_000


def test_opening_from_the_middle_never_pulls_the_whole_head_of_the_menu() -> None:
    """Продолжение с середины тянет заголовок, а не картинку начала.

    Голова под меню - это десятки мегабайт первого сегмента. Возьми их же при продолжении
    с середины - и на холодном рое лишние байты съедят весь бюджет раздумья: пока качается
    чужое начало, до места позиции дело не доходит.
    """
    for container, size in HEAD_OPEN.items():
        assert size < HEAD_WARM, container


def test_the_head_is_sized_by_the_container_and_mkv_is_the_cheap_one() -> None:
    """Одного числа на все контейнеры быть не может - в этом и была ошибка первой версии.

    У mkv в голове лежат EBML-заголовок, SeekHead, Info и Tracks - килобайты; у mp4 там
    ``moov``, и он бывает на мегабайты. Сравняй их - и либо mkv платит за чужие мегабайты,
    либо mp4 не открывается вовсе.
    """
    assert HEAD_OPEN["mkv"] < HEAD_OPEN["mp4"]
    assert HEAD_OPEN["mp4"] >= FATTEST_MOOV_BYTES


def test_an_unknown_container_takes_the_larger_piece_and_not_the_cheaper_one() -> None:
    """Карта из кэша прошлой версии или чужой файл - берём больший кусок.

    Лишние мегабайты дешевле, чем ffmpeg, который не смог открыть вход: там показа не
    будет вовсе, а тут он просто чуть дольше начнётся.
    """
    assert max(HEAD_OPEN.values()) <= HEAD_OPEN_DEFAULT


def test_the_seek_shift_is_told_only_for_the_containers_that_have_a_keyframe_map() -> None:
    """Предсказывать сдвиг ``-ss`` можно только по той карте, из которой он и снят.

    Перемотку обоих демуксеров ведёт тот самый индекс, из которого снята карта (``Cues`` у
    mkv, ``stss`` у mp4). У mpegts карту взять неоткуда, а ведёт он себя наоборот - уезжает
    ВПЕРЁД, - поэтому его в таблице нет намеренно, и появиться он там не должен молча.
    """
    assert SEEK_SHIFT == {"mkv": -1, "mp4": 0}
    assert set(SEEK_SHIFT) == set(HEAD_OPEN), "сдвиг известен ровно там, где известна голова"


def test_the_shelves_are_capped_where_they_stop_growing_and_not_where_they_are_free() -> None:
    """Полка карт весит единицы мегабайт, а паспортов держим больше: они на порядок легче.

    Карта - самый тяжёлый из кэшей рядом с состоянием, паспорт - порядка килобайта, и
    заводится он чаще (снимается и на те релизы, которые показом так и не стали).
    """
    assert KEYS_KEPT * AVERAGE_KEYMAP_BYTES < 10_000_000
    assert PROBE_KEPT > KEYS_KEPT
    assert PROBE_KEPT == 2 * KEYS_KEPT, "полка паспортов названа вдвое большей, а не просто большей"


def test_a_lock_is_never_declared_abandoned_while_someone_is_still_waiting_for_it() -> None:
    """Чужую карту ждут меньше, чем замок считается живым.

    Жди мы дольше срока жизни замка - ожидание упиралось бы в замок, который по своему же
    правилу уже брошен, и два показа принялись бы снимать одну карту разом.
    """
    assert KEYS_WAIT <= KEYS_LOCK


def test_the_warm_is_not_called_hung_while_the_legal_start_is_still_running() -> None:
    """Потолок ожидания прогрева переживает законные сроки старта, а не обрывает их.

    Снятие карты и пробный прогон - это честные фазы с собственными потолками. Опусти
    потолок прогрева ниже их суммы - и висящим объявлялся бы старт, который идёт нормально.
    """
    assert WARM_TIMEOUT >= KEYS_WAIT + PILOT_TIMEOUT
