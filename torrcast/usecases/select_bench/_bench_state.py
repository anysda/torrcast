"""Внешний мир стенда: паспорт потока, прогрев файла, признак жизни роя и отсрочка."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.contact_wait import ContactWait
from torrcast.ports.prober import Prober

#: Внешний мир стенда: чем читается паспорт потока, чем греется файл, чем спрашивается
#: признак жизни роя и чем заводится отсрочка первого контакта. Ни сети, ни диска у
#: самого стенда нет - всё это кладёт композиционный корень (:mod:`torrcast.runtime.wire`).
#: Отсрочка приезжает заводом, а не значением: часы у каждого прогрева свои.
_bench_prober: Prober
_bench_warm_file: Callable[..., None]
_bench_swarm_pulse: Callable[..., Callable[[], bool]]
_bench_contact_wait: Callable[[float], ContactWait]


def _configure_select_bench(
    prober: Prober,
    warm_file: Callable[..., None],
    swarm_pulse: Callable[..., Callable[[], bool]],
    contact_wait: Callable[[float], ContactWait],
) -> None:
    """Назначить стенду отбора его внешний мир."""
    global _bench_prober, _bench_warm_file, _bench_swarm_pulse, _bench_contact_wait
    _bench_prober = prober
    _bench_warm_file = warm_file
    _bench_swarm_pulse = swarm_pulse
    _bench_contact_wait = contact_wait
