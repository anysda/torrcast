"""``cast doctor`` - самопроверка окружения одной командой.

Проверяется ровно то, обо что уже спотыкались: терминал и локаль (кириллица в
вопросах), Prowlarr и TorrServer (есть чем искать и что раздавать), опорные источники,
на которых стоит каталог, адрес ТВ и его порт (есть кому
играть), путь до ТВ и адрес раздачи, mDNS-путь поиска приёмников (будут ли имена),
ffmpeg с ``-readrate_initial_burst`` и серт, если кто-то включил https.

Каждая проверка возвращает пару ``(строка, всё ли хорошо)``. ЧТО СЧИТАЕТСЯ ЗДОРОВЫМ
живёт правилами в :mod:`torrcast.domain`, КАК УЗНАТЬ - за портом
:class:`torrcast.ports.health_environment.HealthEnvironment`; здесь только порядок проб.

⚠️ Среда приходит полем модуля, а не конструктором: её кладёт композиционный корень
(:func:`torrcast.runtime.wire.wire`). Так у проб остаются прежние подписи, а тест
подменяет среду одной пробе аргументом, не трогая соседние.
"""

from collections.abc import Iterator
from functools import partial

import torrcast.usecases.doctor_environment as _state
from torrcast.domain.cache_health import CacheHealth
from torrcast.domain.indexer_health import CORE_INDEXERS, IPV4_ONLY, IndexerHealth
from torrcast.domain.receiver_health import ReceiverHealth
from torrcast.domain.warm_claim import warm_claim
from torrcast.domain.warm_settings import WARM_BUDGET
from torrcast.ports.configuration_source import ConfigurationSource
from torrcast.ports.console import Console
from torrcast.ports.health_checks import HealthChecks
from torrcast.ports.health_config import HealthConfig
from torrcast.ports.health_environment import HealthEnvironment
from torrcast.usecases.disk_free import disk_free as disk_free
from torrcast.usecases.doctor_probe import _TIMEOUT, Env, Line
from torrcast.usecases.doctor_prowlarr import _prowlarr
from torrcast.usecases.host_checkup import HostCheckup
from torrcast.usecases.machine_memory import machine_memory as machine_memory
from torrcast.usecases.show_checkup import ShowCheckup
from torrcast.usecases.warm.settings import FREE_FLOOR
from torrcast.usecases.warm_used import warm_used as warm_used

__all__ = ["CAST_PORT", "CORE_INDEXERS", "IPV4_ONLY", "Doctor", "checkup"]
#: Байты диска, которые кэшу на диске не отдают, когда прогревать ещё нечего: весь бюджет
#: прогрева плюс неприкосновенный запас раздела. То же число складывает установка
#: (``install.sh``: тот же ``WARM_BUDGET`` плюс ``TS_DISK_FLOOR``).
#:
#: 🔴 TC-725. Прогретое, которое уже лежит на диске, из этого числа ВЫЧИТАЕТСЯ
#: (:func:`torrcast.domain.warm_claim.warm_claim`): свободное место раздела его не
#: содержит, и резерв поверх свободного считал бы занятое дважды.
CACHE_DISK_RESERVE = WARM_BUDGET + FREE_FLOOR
#: Порт приёмника кладёт композиционный корень (:func:`torrcast.runtime.wire.wire`); сама
#: среда лежит одна на всех её читателей (:mod:`torrcast.usecases.doctor_environment`).
CAST_PORT: int


def _configure(environment: HealthEnvironment) -> None:
    """Принять системную среду от композиции: без неё пробы не знают внешнего мира."""
    global CAST_PORT
    _state.environment = environment
    CAST_PORT = environment.cast_port()


class Doctor:
    """Сценарий команды ``cast doctor``."""

    def __init__(
        self,
        configuration: ConfigurationSource,
        checks: HealthChecks,
        console: Console,
    ) -> None:
        self._configuration = configuration
        self._checks = checks
        self._console = console

    def run(self) -> int:
        """Печатает проверки и возвращает прежний код команды."""
        bad = 0
        for line, ok in self._checks.check(self._configuration.load()):
            self._console.write(line)
            bad += 0 if ok else 1
        self._console.write("")
        verdict = "всё в порядке" if not bad else f"проблем: {bad} - смотри строки «плохо» выше"
        self._console.write(verdict)
        return 0 if not bad else 2

    @staticmethod
    def checkup(config: HealthConfig, env: Env = None) -> Iterator[Line]:
        """Все проверки по порядку: сначала консоль, потом инфраструктура, потом ТВ."""
        host = HostCheckup(env or _state.environment)
        show = ShowCheckup(env or _state.environment, _TIMEOUT)
        yield host.terminal()
        yield host.locale()
        yield host.ffmpeg()
        yield _family(env)
        yield from _prowlarr(config, env)
        yield show.torrserver(config)
        yield _cache(config, env)
        yield from show.tv(config)
        yield _mdns(env)
        yield show.profile(config)
        yield show.hls(config)
        yield show.shelves()
        yield show.trace()


#: Совместимые имена: команда зовёт проверки одной функцией, а тесты старого модуля
#: подменяют точки ниже по имени - поэтому каждая из них живёт полем модуля.
checkup = Doctor.checkup
_enabled_names = IndexerHealth.enabled_names


def _settings(url: str) -> object | None:
    """Настройки TorrServer спрашивает адаптер среды."""
    return _state.environment.torrserver_settings(url, _TIMEOUT)


def _family(env: Env = None) -> Line:
    """Какой дорогой Prowlarr идёт к трекерам: по IPv4 или как ляжет (TC-311)."""
    return IndexerHealth.route((env or _state.environment).prowlarr_unit(_TIMEOUT))


def _cache(config: HealthConfig, env: Env = None) -> Line:
    """Кэш раздачи: сколько его, во что он обойдётся и влезает ли это в машину."""
    read = _settings if env is None else partial(env.torrserver_settings, timeout=_TIMEOUT)
    memory = machine_memory if env is None else env.machine_memory
    free_of = disk_free if env is None else env.disk_free
    weigh = warm_used if env is None else env.warm_used
    sets = read(config.torrserver_url)
    if not isinstance(sets, dict):
        return CacheHealth.unreadable()
    size = int(sets.get("CacheSize") or 0)
    if not sets.get("UseDisk"):
        return CacheHealth.in_memory(size, memory())
    path = str(sets.get("TorrentsSavePath") or "")
    if not path:
        return CacheHealth.on_disk(size, path, 0, CACHE_DISK_RESERVE)
    reserve = warm_claim(WARM_BUDGET, weigh()) + FREE_FLOOR
    return CacheHealth.on_disk(size, path, free_of(path), reserve)


def _trace(env: Env = None) -> Line:
    """Недельный след: пишется ли он вообще, свежий ли и сколько занимает."""
    return ShowCheckup(env or _state.environment, _TIMEOUT).trace()


def _mdns(env: Env = None) -> Line:
    """Путь поиска приёмников по mDNS: жив ли он, и что именно не так, если имён нет."""
    return ReceiverHealth.mdns(*(env or _state.environment).heard_receivers())
