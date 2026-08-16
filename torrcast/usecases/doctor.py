"""``cast doctor`` - самопроверка окружения одной командой.

Проверяется ровно то, обо что уже спотыкались: терминал и локаль (кириллица в
вопросах), Prowlarr и TorrServer (есть чем искать и что раздавать), метапоиск, на
котором держится западный и аниме-хвост каталога, адрес ТВ и его порт (есть кому
играть), путь до ТВ и адрес раздачи, mDNS-путь поиска приёмников (будут ли имена),
ffmpeg с ``-readrate_initial_burst`` и серт, если кто-то включил https.

Каждая проверка возвращает пару ``(строка, всё ли хорошо)``. ЧТО СЧИТАЕТСЯ ЗДОРОВЫМ
живёт правилами в :mod:`torrcast.domain`, КАК УЗНАТЬ - за портом
:class:`torrcast.ports.health_environment.HealthEnvironment`; здесь только порядок проб.

⚠️ Среда приходит полем модуля, а не конструктором: её кладёт композиция (фасад
:mod:`torrcast.doctor`). Так у проб остаются прежние подписи, а тест подменяет среду
одной пробе аргументом, не трогая соседние.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from torrcast.domain.cache_health import CacheHealth
from torrcast.domain.health_verdict import HealthLine
from torrcast.domain.indexer_health import IPV4_ONLY, KEY_INDEXER, IndexerHealth
from torrcast.domain.receiver_health import ReceiverHealth
from torrcast.ports.configuration_source import ConfigurationSource
from torrcast.ports.console import Console
from torrcast.ports.health_checks import HealthChecks
from torrcast.ports.health_config import HealthConfig
from torrcast.ports.health_environment import HealthEnvironment
from torrcast.usecases.host_checkup import HostCheckup
from torrcast.usecases.show_checkup import ShowCheckup
from torrcast.usecases.warm import FREE_FLOOR, WARM_BUDGET

__all__ = ["CAST_PORT", "IPV4_ONLY", "KEY_INDEXER", "Doctor", "checkup"]

Line = HealthLine
#: Среда пробы: своя у теста, общая у команды.
Env = HealthEnvironment | None
_TIMEOUT = 5.0
#: Живой поиск иногда отвечает дольше обычных проверок: даже без параллельного залпа
#: измеренный медленный ответ выходил за десять секунд.
_INDEXER_TIMEOUT = 15.0
#: Байты диска, которые кэшу на диске не отдают: рядом на том же разделе живёт прогрев со
#: своим бюджетом и запасом, а также состояние и система. То же число складывает
#: установка (``install.sh``: тот же ``WARM_BUDGET`` плюс ``TS_DISK_FLOOR``).
CACHE_DISK_RESERVE = WARM_BUDGET + FREE_FLOOR
#: Оба поля кладёт композиция при импорте фасада ``torrcast.doctor``.
_environment: HealthEnvironment
CAST_PORT: int


def _configure(environment: HealthEnvironment) -> None:
    """Принять системную среду от композиции: без неё пробы не знают внешнего мира."""
    global _environment, CAST_PORT
    _environment = environment
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
        host = HostCheckup(env or _environment)
        show = ShowCheckup(env or _environment, _TIMEOUT)
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


def _json(url: str, headers: dict[str, str]) -> object | None:
    """JSON у Prowlarr спрашивает адаптер среды."""
    return _environment.get_json(url, headers, _TIMEOUT)


def _settings(url: str) -> object | None:
    """Настройки TorrServer спрашивает адаптер среды."""
    return _environment.torrserver_settings(url, _TIMEOUT)


def machine_memory() -> int:
    """Память машины меряет адаптер среды."""
    return _environment.machine_memory()


def disk_free(path: str) -> int:
    """Место на разделе меряет адаптер среды."""
    return _environment.disk_free(path)


def _family(env: Env = None) -> Line:
    """Какой дорогой Prowlarr идёт к трекерам: по IPv4 или как ляжет (TC-311)."""
    return IndexerHealth.route((env or _environment).prowlarr_unit(_TIMEOUT))


def _prowlarr(config: HealthConfig, env: Env = None) -> Iterator[Line]:
    """Prowlarr: отвечает ли, сколько индексеров и жив ли тот, что весит за половину."""
    ask = _json if env is None else partial(env.get_json, timeout=_TIMEOUT)
    if not config.prowlarr_apikey:
        yield IndexerHealth.no_apikey()
        return
    headers = {"X-Api-Key": config.prowlarr_apikey}
    if ask(f"{config.prowlarr_url}/api/v1/health", headers) is None:
        yield IndexerHealth.silent(config.prowlarr_url)
        return
    indexers = ask(f"{config.prowlarr_url}/api/v1/indexer", headers)
    count = len(indexers) if isinstance(indexers, list) else 0
    yield IndexerHealth.count(config.prowlarr_url, count)
    if not count:
        return
    statuses = ask(f"{config.prowlarr_url}/api/v1/indexerstatus", headers)
    yield from IndexerHealth.paused(indexers, statuses)
    yield from _live_indexers(config, indexers, env)
    yield IndexerHealth.key(indexers)


def _live_indexers(config: HealthConfig, payload: object, env: Env = None) -> Iterator[Line]:
    """По одному настоящему поиску на индексер без одновременного залпа."""
    pairs = IndexerHealth.probed(payload)
    probe = _probe_indexer if env is None else partial(_probe_indexer, env=env)
    with ThreadPoolExecutor(max_workers=1) as pool:
        answers = list(pool.map(lambda pair: probe(config, *pair), pairs))
    for (_, name), answer in zip(pairs, answers, strict=True):
        yield IndexerHealth.answered(name, answer)


def _probe_indexer(config: HealthConfig, indexer: int, name: str, env: Env = None) -> str:
    """Ответ индексера на живой поиск: ответил, ответил мимо или промолчал."""
    query = IndexerHealth.query(name)
    titles = (env or _environment).search_titles(
        config.prowlarr_url, config.prowlarr_apikey, indexer, query, _INDEXER_TIMEOUT
    )
    return IndexerHealth.answer(query, titles)


def _cache(config: HealthConfig, env: Env = None) -> Line:
    """Кэш раздачи: сколько его, во что он обойдётся и влезает ли это в машину."""
    read = _settings if env is None else partial(env.torrserver_settings, timeout=_TIMEOUT)
    memory = machine_memory if env is None else env.machine_memory
    free_of = disk_free if env is None else env.disk_free
    sets = read(config.torrserver_url)
    if not isinstance(sets, dict):
        return CacheHealth.unreadable()
    size = int(sets.get("CacheSize") or 0)
    if not sets.get("UseDisk"):
        return CacheHealth.in_memory(size, memory())
    path = str(sets.get("TorrentsSavePath") or "")
    return CacheHealth.on_disk(size, path, free_of(path) if path else 0, CACHE_DISK_RESERVE)


def _trace(env: Env = None) -> Line:
    """Недельный след: пишется ли он вообще, свежий ли и сколько занимает."""
    return ShowCheckup(env or _environment, _TIMEOUT).trace()


def _mdns(env: Env = None) -> Line:
    """Путь поиска приёмников по mDNS: жив ли он, и что именно не так, если имён нет."""
    return ReceiverHealth.mdns(*(env or _environment).heard_receivers())
