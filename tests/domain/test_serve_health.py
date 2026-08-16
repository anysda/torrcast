"""Зеркало :mod:`torrcast.domain.serve_health`."""

from torrcast.domain.serve_health import ServeHealth


def test_a_broken_base_names_the_reason() -> None:
    """Адрес раздачи не собрался - в строке причина, а не трейсбек."""
    line, ok = ServeHealth.hls("", "не вижу маршрута до ТВ", False, "/etc/cert", None)
    assert not ok and "не вижу маршрута" in line, line


def test_plain_http_needs_neither_a_cert_nor_dns() -> None:
    """Дефолтный транспорт - это отсутствие серта в пути показа, и это «ок»."""
    line, ok = ServeHealth.hls("http://10.0.0.7:8080", "", False, "/etc/cert", None)
    assert ok and "ни серта, ни DNS" in line


def test_an_unreadable_cert_under_https_is_a_failure() -> None:
    line, ok = ServeHealth.hls("https://tv", "", True, "/etc/cert", None)
    assert not ok and "не читается" in line, line


def test_a_cert_about_to_expire_is_a_failure_and_a_fresh_one_is_not() -> None:
    """Меньше недели - чинить придётся в тот вечер, когда сядут смотреть."""
    assert ServeHealth.hls("https://tv", "", True, "/etc/cert", 6)[1] is False
    line, ok = ServeHealth.hls("https://tv", "", True, "/etc/cert", 30)
    assert ok and "осталось 30 дн" in line


def test_shelves_show_both_the_count_and_the_ceiling() -> None:
    """«Много» и «мало» должны читаться без документации - потолок стоит рядом."""
    line, ok = ServeHealth.shelves("/var/lib/torrcast", (7, 2_000_000), 200, (3, 1_000_000), 300)
    assert ok and "карт 7/200" in line and "паспортов 3/300" in line
    assert "2.0 МБ" in line and "1.0 МБ" in line


def test_the_age_of_a_record_is_said_in_the_fitting_unit() -> None:
    assert ServeHealth.ago(120) == "2 мин"
    assert ServeHealth.ago(7200) == "2 ч"
    assert ServeHealth.ago(2 * 86400) == "2 дн"


def test_a_missing_journal_is_a_warning_with_its_directory() -> None:
    """Ленты нет - разбирать прошлый сеанс будет нечем, но показу это не мешает."""
    line, ok = ServeHealth.trace(False, 0.0, 0, "/var/lib/torrcast/log", 7)
    assert ok and "/var/lib/torrcast/log" in line and "следа нет" in line


def test_a_stale_journal_says_how_long_ago_it_stopped() -> None:
    line, ok = ServeHealth.trace(True, 30 * 86400, 2_000_000, "/log", 7)
    assert ok and "30 дн назад" in line and "2.0 МБ" in line


def test_a_living_journal_is_ok_and_carries_its_weight() -> None:
    line, ok = ServeHealth.trace(True, 3600, 2_000_000, "/log", 7)
    assert ok and line.startswith("ок") and "1 ч назад" in line
