"""Поля приёмника: адрес обязателен, часы и профиль - свои у каждого приёмника."""

from __future__ import annotations

import pytest

from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.cast.receiver_state import _State
from torrcast.adapters.system_clock import SystemClock
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, Profile


def test_a_receiver_without_an_address_refuses_to_exist_with_a_way_out() -> None:
    """Пустой адрес - это не приёмник, и человеку сразу сказано, чем его найти.

    Молчаливый приёмник с пустым адресом уехал бы дальше и умер бы на подключении -
    там, где подсказать про поиск телевизоров уже некому.
    """
    with pytest.raises(InfraError, match="cast --tv"):
        _State("")


def test_the_default_profile_is_the_cautious_one_and_the_clock_is_the_real_one() -> None:
    """Показ без выбранного профиля ведёт себя как раньше, а выдержки идут по стенным часам."""
    receiver = _State("10.0.0.50")

    assert receiver.profile is CAUTIOUS
    assert isinstance(receiver.clock, SystemClock)


def test_a_dry_run_gets_its_own_profile_and_its_own_clock() -> None:
    """Сухому прогону дают свои часы, чтобы не выжидать минуты терпения по-настоящему."""
    clock = FakeClock()
    profile = Profile(key="stick", title="приставка")

    receiver = _State("10.0.0.50", profile=profile, clock=clock)

    assert receiver.profile is profile
    assert receiver.clock is clock


def test_the_watchdog_starts_from_a_clean_slate() -> None:
    """Счётчики сторожа заводятся пустыми, а «ничего не было» помечено отрицанием.

    Ноль тут был бы законным местом фильма: показ, начатый с 0:00, неотличим от «мы
    ещё ничего не видели», и сторож принял бы такой ноль за перемотку в начало.
    """
    receiver = _State("10.0.0.50")

    assert receiver._seen == -1.0
    assert receiver._stall_at == -1.0
    assert receiver._nudged_to == -1.0
    assert receiver._skip_from == -1.0
    assert receiver._error_code is None
    assert receiver._deaths == {}
    assert receiver.next_cut is None
    # А вот пройденный максимум и незакрытая перемотка начинаются с нуля: это места
    # фильма, и «минус один» тут значил бы секунду до начала картины.
    assert receiver._peak == 0.0
    assert receiver._seek_from == 0.0 and receiver._seek_to == 0.0
    assert receiver._seek_since == 0.0
    assert receiver._stall_hits == 0 and receiver._blind == 0 and receiver._reloads == 0
    assert receiver._stall_since == 0.0 and receiver._at == 0.0
    assert receiver._started is False, "первый показ ждёт картинку по бюджету старта"
    assert receiver._gone is False and receiver._cast is None


def test_two_receivers_do_not_share_the_count_of_deaths() -> None:
    """Счёт смертей по кускам - у каждого приёмника свой: сетка у каждой картины своя."""
    first, second = _State("10.0.0.50"), _State("10.0.0.60")
    first._deaths[10.0] = 3

    assert second._deaths == {}
