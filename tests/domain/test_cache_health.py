"""Зеркало :mod:`torrcast.domain.cache_health`."""

import pytest

from torrcast.domain.cache_health import CACHE_ON_DISK_MEMORY, CacheHealth


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русское словоблюдие самопроверки, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английские надписи, а рассказывал бы про русские.
    """


def test_a_silent_torrserver_is_a_failure() -> None:
    """Без службы раздачи показывать нечего - это «плохо», а не «внимание»."""
    line, ok = CacheHealth.server("http://127.0.0.1:8090", None)
    assert not ok and "не отвечает" in line, line


def test_a_living_torrserver_shows_its_answer_short() -> None:
    """Ответ службы - это её версия: в строку берём только начало."""
    line, ok = CacheHealth.server("http://x", "  MatriX.130 " + "!" * 40)
    assert ok and "MatriX.130" in line
    assert "!" * 20 not in line


def test_unreadable_settings_do_not_fail_the_checkup() -> None:
    """Молчащие настройки - «внимание»: про саму службу сказала строка выше."""
    line, ok = CacheHealth.unreadable()
    assert ok and "неизвестен" in line, line


def test_a_cache_that_fits_the_machine_is_a_line_with_numbers() -> None:
    """3 ГиБ кэша на 8 ГиБ машины - это норма, а не поломка."""
    line, ok = CacheHealth.in_memory(3 * 1024**3, 8 * 1024**3)
    assert ok, line
    assert "3.0 ГиБ" in line and "8.0 ГиБ" in line, f"размер и память обязаны быть видны: {line}"


def test_a_cache_twice_its_own_weight_does_not_fit() -> None:
    """Тот самый случай: 4 ГиБ кэша на 8 ГиБ машины - показ уронит машину."""
    line, ok = CacheHealth.in_memory(4 * 1024**3, 8 * 1024**3)
    assert not ok and "не влезает" in line, line


def test_a_cache_on_disk_is_not_measured_by_memory() -> None:
    """Замер: кэш на диске стоит службе сотню мегабайт при любом своём размере."""
    line, ok = CacheHealth.on_disk(12 * 1024**3, "/var/cache", 60 * 1024**3, 20 * 1024**3)
    assert ok, line
    assert "на диске" in line and "12.0 ГиБ" in line, line
    assert CacheHealth.gib(CACHE_ON_DISK_MEMORY) in line


def test_a_disk_without_room_for_the_warmup_is_bad() -> None:
    """Раздел, где кэшу место есть, а прогреву уже нет, - это «плохо»."""
    line, ok = CacheHealth.on_disk(4 * 1024**3, "/var/cache", 30 * 1024**3, 40 * 1024**3)
    assert not ok and "прогреву места не остаётся" in line, line


def test_a_cache_on_disk_without_a_path_is_bad() -> None:
    """``UseDisk`` без пути - служба кладёт кэш куда сама решит, и это не наш раздел."""
    line, ok = CacheHealth.on_disk(4 * 1024**3, "", 0, 0)
    assert not ok and "путь не задан" in line, line


def test_an_unreadable_partition_is_a_warning() -> None:
    """Место не читается - сравнивать не с чем, но и падать не с чего."""
    line, ok = CacheHealth.on_disk(4 * 1024**3, "/var/cache", 0, 1)
    assert ok and "не читается" in line, line


def test_bytes_are_shown_to_a_human_in_gibibytes() -> None:
    assert CacheHealth.gib(1536 * 1024**2) == "1.5 ГиБ"
