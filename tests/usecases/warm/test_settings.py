"""Пороги прогрева: числа, на которых держатся уступка, сверка и разбор куска."""

from __future__ import annotations

from torrcast.usecases.warm.settings import (
    CHAIN_RETRY,
    FREE_FLOOR,
    GUARD_HIGH,
    GUARD_LOW,
    HEAD_BYTES,
    META,
    PCR_CLOCK,
    PES_CLOCK,
    RUN_DIR,
    SKEW_MAX,
    SKEW_TRIES,
    START_GRACE,
    STARVE_GRACE,
    TS_PACKET,
    TS_SYNC,
    WARM_ENV,
    WARM_NICE,
    WARM_RATE,
)


def test_the_yield_thresholds_keep_their_hysteresis() -> None:
    """Порог заморозки ниже порога оживления: без зазора прогрев дёргался бы стоп/старт."""
    assert 0 < GUARD_LOW < GUARD_HIGH, "гистерезис уступки схлопнулся"
    assert 0 < STARVE_GRACE < GUARD_HIGH, "выдержка здоровья не короче самого оживления"
    assert START_GRACE >= GUARD_HIGH, "ожидание картинки короче запаса, которого оно ждёт"


def test_the_pace_is_polite_and_the_priority_is_the_lowest() -> None:
    """Темп быстрее реального времени, но не «во весь опор», а ``nice`` - самый вежливый."""
    assert 1.0 < WARM_RATE <= 8.0, "темп прогрева перестал быть вежливым к раздаче"
    assert WARM_NICE == 19, "прогрев больше не самый вежливый процесс в системе"


def test_the_disk_floor_and_the_retry_are_named_in_their_own_units() -> None:
    """Запас раздела считается гигабайтами, а повтор цепочки - секундами."""
    assert FREE_FLOOR == 3 << 30, "неприкосновенный запас раздела сместился"
    assert CHAIN_RETRY >= 10.0, "повтор сборки следующей серии стал долбёжкой раздачи"


def test_the_skew_watchdog_catches_a_defect_not_a_jitter() -> None:
    """Порог сдвига вмещает дрожание меток (сотые доли) и ловит поломку (секунды)."""
    assert 0.04 < SKEW_MAX < 1.0, "порог сдвига перестал отделять кадр от поломки"
    assert SKEW_TRIES == 2, "число попыток переложить место изменилось"


def test_the_transport_numbers_are_the_mpeg_ones() -> None:
    """Разбор головы куска стоит на константах MPEG-TS, а не на догадках."""
    assert TS_PACKET == 188 and TS_SYNC == 0x47, "пакет TS перестал быть пакетом TS"
    assert PCR_CLOCK == PES_CLOCK * 300, "часы PCR разошлись с часами PES"
    assert HEAD_BYTES == 64 << 10 and HEAD_BYTES > 100 * TS_PACKET, "голова куска сжалась"


def test_the_names_on_disk_stay_the_ones_the_show_looks_for() -> None:
    """Паспорт и каталог прогона зовутся так, как их ищут показ и бюджет."""
    assert META == "warm.json" and RUN_DIR == "run"
    assert WARM_ENV == "TORRCAST_WARM", "переопределение каталога сменило имя"
