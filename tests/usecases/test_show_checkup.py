"""Пробы пути показа: раздача, ТВ, профиль, полки и след - на двойнике среды."""

from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.domain.settings import Settings
from torrcast.usecases.show_checkup import ShowCheckup


def _checkup(environment: FakeHealthEnvironment) -> ShowCheckup:
    return ShowCheckup(environment, 5.0)


def test_a_silent_torrserver_is_a_failure_with_its_address() -> None:
    environment = FakeHealthEnvironment(echo=None)
    line, ok = _checkup(environment).torrserver(Settings())
    assert not ok and "не отвечает" in line
    assert environment.timeouts == [5.0], "срок ожидания задаёт сценарий, а не адаптер"


def test_an_unnamed_tv_ends_the_receiver_probe_at_once() -> None:
    """Адреса нет - маршрут и порт спрашивать не у чего."""
    environment = FakeHealthEnvironment()
    lines = list(_checkup(environment).tv(Settings(tv="")))
    assert len(lines) == 1 and not lines[0][1]
    assert environment.timeouts == []


def test_a_mock_receiver_stops_the_probe_before_the_network() -> None:
    lines = list(_checkup(FakeHealthEnvironment()).tv(Settings(tv="10.0.0.50", receiver="mock")))
    assert [ok for _, ok in lines] == [True]
    assert "mock" in lines[0][0]


def test_a_tv_without_a_route_never_gets_its_port_probed() -> None:
    environment = FakeHealthEnvironment(address="")
    lines = list(_checkup(environment).tv(Settings(tv="10.0.0.50")))
    assert len(lines) == 1 and not lines[0][1]
    assert environment.timeouts == []


def test_a_visible_tv_is_probed_by_its_port() -> None:
    environment = FakeHealthEnvironment(refusal="Connection refused")
    lines = list(_checkup(environment).tv(Settings(tv="10.0.0.50")))
    assert [ok for _, ok in lines] == [True, False]
    assert "8009" in lines[1][0] and "Connection refused" in lines[1][0]


def test_http_delivery_never_asks_about_a_cert() -> None:
    """Серт спрашивается только под https - иначе его отсутствие ничего не значит."""
    environment = FakeHealthEnvironment(days=None)
    line, ok = _checkup(environment).hls(Settings())
    assert ok and "ни серта" in line


def test_https_delivery_is_judged_by_the_days_left() -> None:
    environment = FakeHealthEnvironment(base=("https://tv", ""), days=3)
    line, ok = _checkup(environment).hls(Settings(transport="https"))
    assert not ok and "осталось 3 дн" in line


def test_a_broken_base_is_not_asked_about_a_cert_either() -> None:
    environment = FakeHealthEnvironment(base=("", "не вижу маршрута до ТВ"), days=90)
    line, ok = _checkup(environment).hls(Settings(transport="https"))
    assert not ok and "не вижу маршрута" in line


def test_the_profile_line_comes_from_the_receiver_passport() -> None:
    environment = FakeHealthEnvironment(profile=("осторожный", "нет паспорта", True))
    assert _checkup(environment).profile(Settings())[0].startswith("ок"), "не «беру осторожный»"


def test_shelves_show_counts_against_their_ceilings() -> None:
    environment = FakeHealthEnvironment(shelf=("/полка", (7, 0), (3, 0)), limits=(200, 300))
    line, ok = _checkup(environment).shelves()
    assert ok and "карт 7/200" in line and "паспортов 3/300" in line


def test_the_journal_age_is_counted_from_the_environment_clock() -> None:
    """Часы у сценария не свои: возраст записи считает та же среда, что и всё прочее."""
    environment = FakeHealthEnvironment(journal=(True, 1000.0, 2_000_000), moment=1000.0 + 7200)
    line, ok = _checkup(environment).trace()
    assert ok and "2 ч назад" in line
