"""Порт обновления собирает права, установленный загрузчик и его запуск."""

from tests.fakes.upgrade_environment import FakeUpgradeEnvironment
from torrcast.ports.upgrade_environment import UpgradeEnvironment


def test_upgrade_environment_is_protocol() -> None:
    assert UpgradeEnvironment.__name__ == "UpgradeEnvironment"


def test_the_port_asks_for_rights_the_loader_and_the_hand_off() -> None:
    for member in ("is_root", "loader", "hand_off"):
        assert hasattr(UpgradeEnvironment, member), member


def test_the_stand_double_answers_the_whole_port() -> None:
    """Подставка сценария сверяется с портом, а не сама с собой.

    Метод, забытый в подставке, иначе разошёлся бы с живым адаптером молча: сценарий
    зелен на стенде и падает у человека на первом же вызове.
    """
    double = FakeUpgradeEnvironment()
    for member in ("is_root", "loader", "hand_off"):
        assert callable(getattr(double, member, None)), member
