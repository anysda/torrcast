"""Зеркало :mod:`torrcast.domain.probe_settings`: сроки опроса служб и глубина цвета.

Сторожатся две связи. Вопрос на краю показа обязан быть дешёвым: пока мы ждём ответа, экран
уже гаснет, и человеку нужна строка, а не наше терпение. А глубина цвета - это замер
ПРИЁМНИКА, и живёт он в его профиле, а не второй копией рядом.
"""

from __future__ import annotations

from torrcast.domain.pick_settings import META_BUDGET
from torrcast.domain.probe_settings import COPY_DEPTH, META_GRACE, PROBE_TIMEOUT
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.worker_settings import WORKER_META


def test_asking_a_dying_show_costs_far_less_than_asking_the_same_service_under_the_menu() -> None:
    """Срок вопроса на краю показа кратно короче бюджета той же службы под меню.

    Под меню человек ждёт выбора и платит за это секундами очереди. На краю показа он ждёт
    строку о том, что случилось: там долгий срок вреден напрямую - экран уже погас, а мы
    всё ещё терпим. Перезапуск службы (3.0-3.1 с) и её паника (5 с) ловятся не длинным
    сроком одного вопроса, а повторным вопросом.
    """
    assert PROBE_TIMEOUT * 5 <= META_BUDGET


def test_a_returning_torrent_gets_more_time_than_a_single_ask_takes() -> None:
    """Отсрочка на метаданные обязана быть заметно длиннее самого опроса.

    Раздача, добавленная магнитом заново, секунду-другую стоит без списка файлов - рой
    только собирается. Сравняй отсрочку с длиной опроса - и показ на КАЖДОМ вопросе снова
    считал бы её раздачей по голому хэшу и добавлял магнит поверх едущих метаданных.
    """
    assert META_GRACE >= 5 * PROBE_TIMEOUT


def test_the_grace_ends_before_the_unit_itself_stops_waiting_for_metadata() -> None:
    """Отсрочка обязана кончиться раньше, чем ждать метаданные перестаёт сам юнит.

    Отсрочка говорит «раздача ещё собирает рой, не считай её пустышкой». Юнит же ждёт
    метаданные до своего последнего рубежа, и дальше показывать нечего. Дай отсрочке
    пережить этот рубеж - и раздача числилась бы «ещё едущей» уже после того, как показ
    сдался: магнит добавлялся бы поверх того, чего никто не ждёт.
    """
    assert META_GRACE < WORKER_META


def test_the_depth_measurement_is_the_receivers_profile_and_not_a_copy_beside_it() -> None:
    """Глубина цвета - свойство приёмника, и берётся она у него.

    Заведись здесь вторая копия этого числа - показ пошёл бы по профилю живого приёмника, а
    щупы и умолчания мерили бы прежнюю границу, и замер перестал бы значить что-либо.
    """
    assert CAUTIOUS.copy_depth == COPY_DEPTH


def test_the_name_of_the_codec_is_never_enough_to_decide_on_a_copy() -> None:
    """H.264 бывает десятибитным, зовётся тем же именем - и приёмник его не декодирует.

    Поэтому решение принимается по ПАРЕ «кодек и глубина»: имя вне набора перекода само по
    себе копии не обещает. Сведи правило к членству в наборе - и вернётся вечная петля
    «залип, закрываю приложение, LOAD, BUFFERING».
    """
    assert "h264" not in CAUTIOUS.recode_codecs
    assert CAUTIOUS.plays_copy("h264", COPY_DEPTH)
    assert not CAUTIOUS.plays_copy("h264", COPY_DEPTH + 2)
