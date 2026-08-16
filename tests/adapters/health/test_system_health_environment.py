"""Проверяет, что системная среда закрывает порт самопроверки целиком."""

from torrcast.adapters.health.machine_probe import MachineProbe
from torrcast.adapters.health.service_probe import ServiceProbe
from torrcast.adapters.health.system_health_environment import SystemHealthEnvironment
from torrcast.ports.health_environment import HealthEnvironment


def test_the_environment_answers_every_question_of_the_port() -> None:
    """Порт спрашивает про машину и про службы разом, а спрашиваются они порознь."""
    asked = {name for name in vars(HealthEnvironment) if not name.startswith("_")}
    assert asked
    assert asked <= set(dir(SystemHealthEnvironment))


def test_the_environment_adds_nothing_of_its_own() -> None:
    """Своих методов у сборки нет: она только сводит две половины проб."""
    assert not {name for name in vars(SystemHealthEnvironment) if not name.startswith("_")}
    assert SystemHealthEnvironment.__mro__[1:3] == (MachineProbe, ServiceProbe)
