"""Системная среда самопроверки: одно место, где она лежит между корнем и пробами.

Кладёт её композиция (:func:`torrcast.usecases.doctor._configure`), читают пробы
(:mod:`torrcast.usecases.doctor`) и две мерки машины
(:mod:`torrcast.usecases.machine_memory`, :mod:`torrcast.usecases.disk_free`).
"""

from __future__ import annotations

from torrcast.ports.health_environment import HealthEnvironment

#: До слова композиции имени тут нет вовсе: молчаливой подделки у системы не бывает.
environment: HealthEnvironment
