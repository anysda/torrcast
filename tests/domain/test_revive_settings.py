"""Зеркало :mod:`torrcast.domain.revive_settings`: чем и как часто поднимают погасший показ.

Сторожатся связи, а не числа: запас попыток нельзя восполнять быстрее, чем он тратится,
все попытки обязаны укладываться в окно, пока экран ещё занят нашим приложением, а круг
вопросов источнику - перекрывать замеренную паузу самой службы.
"""

from __future__ import annotations

from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.domain.revive_settings import (
    REVIVE_DROP,
    REVIVE_LIMIT,
    REVIVE_LIVED,
    REVIVE_PAUSE,
    REVIVE_TRIES,
    SOURCE_PAUSE,
    SOURCE_TRIES,
)
from torrcast.domain.start_settings import PAUSE_LIMIT

#: Замеренная паника службы-источника: столько она отвечает как живая, ничего не отдавая.
SOURCE_PANIC_SECONDS = 5.0


def test_a_blinking_show_can_never_earn_tries_faster_than_it_spends_them() -> None:
    """Запас попыток восполняется НЕ быстрее, чем тратится, иначе LOAD идёт вечно.

    Опусти срок жизни ниже выдержки - и показ, который поднялся и тут же погас, возвращал
    бы себе попытку раньше, чем истратил следующую: приёмник гонялся бы по кругу без конца
    и без права честно погаснуть.
    """
    assert REVIVE_LIVED >= REVIVE_PAUSE


def test_a_dropped_show_gets_a_reserve_of_tries_and_not_a_single_shot() -> None:
    """Попытка обязана быть не одна, иначе воскрешать нечем и модуль ничего не решает.

    Запас нужен ровно потому, что обрыв бывает случайным: приёмник теряет сессию, рой
    проваливается на секунды. Оставь одну попытку - и показ, который поднялся бы со
    второго раза, гас бы насовсем; убери запас вовсе - и погасший показ не поднимался бы
    никогда. Сверху запас держит окно занятого экрана (тест ниже), поэтому здесь стоит
    только нижняя граница: у числа обязаны быть обе.
    """
    assert REVIVE_TRIES >= 2


def test_all_the_tries_fit_into_the_window_while_our_app_still_holds_the_screen() -> None:
    """Три попытки обязаны уложиться, пока экран ещё занят нашим же приложением.

    Приёмник держит экран 301 с после смерти медиасессии. Выйди последняя попытка за это
    окно - она уходила бы уже в чужой экран, то есть не в тот показ, который поднимаем.
    """
    last_try_at = REVIVE_DROP + (REVIVE_TRIES - 1) * REVIVE_PAUSE
    assert last_try_at < CAUTIOUS.app_patience


def test_the_first_try_in_a_receiver_made_darkness_is_the_fast_one() -> None:
    """Темноту, устроенную самим приёмником, ждут секунды, а не минуту.

    Замер: приёмник, только что погасивший показ, берёт LOAD через 3-4 с. Минута тут была
    минутой чёрного экрана впустую; меньше замеренных трёх секунд ставить тоже нечего -
    раньше приёмник LOAD не возьмёт.
    """
    assert 3.0 <= REVIVE_DROP < REVIVE_PAUSE


def test_the_darkness_outlives_the_receiver_and_ends_long_before_a_pause_does() -> None:
    """Потолок темноты вчетверо длиннее терпения приёмника и вчетверо короче терпения к паузе.

    Опусти его к терпению приёмника - и обычный обрыв кончал бы показ раньше, чем показ
    успел бы вернуться; подними к потолку паузы - и tmpfs с раздачей держались бы часами
    ради пустого экрана.
    """
    assert CAUTIOUS.app_patience < REVIVE_LIMIT
    assert REVIVE_LIMIT * 4 == PAUSE_LIMIT


def test_the_round_of_questions_to_the_source_outlives_its_measured_panic() -> None:
    """Круг вопросов источнику обязан перекрыть замеренное окно, где он врёт, что жив.

    Перезапуск службы стоит 3.0-3.1 с недоступности, её паника - 5 с, и внутри этого окна
    она отвечает как живая. Сократи круг - и показ обвинил бы в аварии приёмник, хотя
    виноват был источник.
    """
    assert (SOURCE_TRIES - 1) * SOURCE_PAUSE >= SOURCE_PANIC_SECONDS


def test_the_relaxation_measured_on_the_stick_never_moves_the_cautious_default() -> None:
    """Выдержки берутся из осторожного профиля, и послабление приставки их не двигает.

    У приставки те же выдержки короче (её замеры - её дело), но умолчание модуля обязано
    оставаться осторожным: приёмник, про который мы ничего не знаем, получает осторожный
    набор, а не смелый.
    """
    assert CAUTIOUS.revive_pause == REVIVE_PAUSE
    assert CAUTIOUS.revive_drop == REVIVE_DROP
    assert ANDROID_TV.revive_pause < REVIVE_PAUSE
    assert ANDROID_TV.revive_drop > REVIVE_DROP
