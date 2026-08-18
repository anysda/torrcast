"""Системная среда самопроверки: обе половины проб под одним портом.

Собирается композиционным корнем (:func:`torrcast.runtime.wire.wire`) и отдаётся
сценарию :mod:`torrcast.usecases.doctor` целиком.
"""

from torrcast.adapters.health.machine_probe import MachineProbe
from torrcast.adapters.health.service_probe import ServiceProbe


class SystemHealthEnvironment(MachineProbe, ServiceProbe):
    """Всё, что ``cast doctor`` узнаёт снаружи себя, одним объектом.

    Своих методов нет вовсе: машина и службы спрашиваются раздельно, а порт
    :class:`torrcast.ports.health_environment.HealthEnvironment` требует их вместе.
    """
