"""Общее у всех проб самопроверки: как зовётся строка ответа, чья среда и сколько её ждут.

Читают их пробы (:mod:`torrcast.usecases.doctor`, :mod:`torrcast.usecases.doctor_prowlarr`).
"""

from __future__ import annotations

from torrcast.domain.health_verdict import HealthLine
from torrcast.ports.health_environment import HealthEnvironment

Line = HealthLine
#: Среда пробы: своя у теста, общая у команды.
Env = HealthEnvironment | None
_TIMEOUT = 5.0
#: Живой поиск иногда отвечает дольше обычных проверок: даже без параллельного залпа
#: измеренный медленный ответ выходил за десять секунд.
_INDEXER_TIMEOUT = 15.0
