"""Зеркало :mod:`torrcast.domain.receiver_health`."""

from torrcast.domain.receiver_health import ReceiverHealth


def test_an_unnamed_tv_is_a_failure_with_a_recipe() -> None:
    """Адреса нет - показывать некуда, и строка сразу говорит, чем это лечится."""
    line, ok = ReceiverHealth.unnamed()
    assert not ok and "cast --tv" in line, line


def test_a_mock_receiver_is_a_warning_because_it_is_a_mode() -> None:
    """Заглушка - это режим проверки, а не поломка окружения."""
    line, ok = ReceiverHealth.mock("10.0.0.50")
    assert ok and line.startswith("внимание") and "10.0.0.50" in line


def test_a_route_names_the_leg_we_are_seen_from() -> None:
    """У хоста несколько ног: в строке должна быть та, которую видит ТВ."""
    line, ok = ReceiverHealth.route("10.0.0.50", "10.0.0.7")
    assert ok and "10.0.0.7" in line
    dead, ok = ReceiverHealth.route("10.0.0.50", "")
    assert not ok and "нет маршрута" in dead


def test_a_closed_port_asks_about_the_power() -> None:
    """Порт 8009 открыт даже у спящего Q70D - закрытый значит обесточенный."""
    line, ok = ReceiverHealth.port(8009, "Connection refused")
    assert not ok and "Connection refused" in line and "обесточен" in line
    assert ReceiverHealth.port(8009, "")[1] is True


def test_heard_receivers_are_named_in_the_line() -> None:
    """Смысл mDNS - имена: они и должны быть видны, но не больше трёх."""
    line, ok = ReceiverHealth.mdns(["Q70D", "кухня", "спальня", "гараж"], "", "")
    assert ok and line.startswith("ок")
    assert "приёмников 4" in line and "гараж" not in line


def test_silence_in_the_air_is_a_warning_and_a_missing_module_is_not() -> None:
    """Тишина - свойство сети, а отсутствие zeroconf - сломанная установка."""
    quiet, ok = ReceiverHealth.mdns([], "silence", "mDNS слушал 4 сек - тишина")
    assert ok and quiet.startswith("внимание") and "тишина" in quiet
    broken, ok = ReceiverHealth.mdns([], "module", "mDNS не слушаю: нет zeroconf")
    assert not ok and broken.startswith("плохо") and "zeroconf" in broken


def test_a_cautious_profile_on_an_unknown_receiver_asks_for_a_name() -> None:
    """Осторожный набор у неопрошенного приёмника - единственный случай подсказки."""
    line, ok = ReceiverHealth.profile("осторожный", "приёмник не ответил - беру осторожный", True)
    assert ok and line.startswith("внимание") and "receiver_profile" in line


def test_a_known_profile_is_just_a_line_with_its_origin() -> None:
    """Профиль по паспорту - «ок», и в строке видно, откуда он взялся."""
    line, ok = ReceiverHealth.profile("Q70D", "по паспорту: Samsung", False)
    assert ok and "по паспорту: Samsung" in line and "receiver_profile" not in line


def test_a_cautious_profile_named_by_hand_is_not_a_warning() -> None:
    """Осторожный набор, названный руками, - это решение человека, а не наша беда."""
    line, ok = ReceiverHealth.profile(
        "осторожный", "назван руками: receiver_profile=cautious", True
    )
    assert ok and line.startswith("ок"), line
