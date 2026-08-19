"""Пробы Prowlarr: отвечает ли он, сколько у него индексеров и живы ли они на самом деле.

Порядок проб держит :meth:`torrcast.usecases.doctor.Doctor.checkup`, здесь - сами пробы.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import torrcast.usecases.doctor_environment as _state
from torrcast.domain.indexer_health import IndexerHealth
from torrcast.ports.health_config import HealthConfig
from torrcast.usecases.doctor_probe import _INDEXER_TIMEOUT, _TIMEOUT, Env, Line


def _json(url: str, headers: dict[str, str]) -> object | None:
    """JSON у Prowlarr спрашивает адаптер среды."""
    return _state.environment.get_json(url, headers, _TIMEOUT)


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
    titles = (env or _state.environment).search_titles(
        config.prowlarr_url, config.prowlarr_apikey, indexer, query, _INDEXER_TIMEOUT
    )
    return IndexerHealth.answer(query, titles)
