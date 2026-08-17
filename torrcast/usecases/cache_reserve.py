"""Запас показа в кэше службы раздач, языком зрителя: минуты, а не гигабайты.
Спрашивает его ``cast status`` через сеанс показа; горячий путь показа сюда не ходит.
"""

from __future__ import annotations

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.probe_settings import PROBE_TIMEOUT
from torrcast.ports.torrent_engines import TorrentEngines

#: Чем сценарий берёт службу раздач: адрес и срок ответа - его, сама служба - не его.
#: Кладёт сюда композиционный корень (:mod:`torrcast.runtime.wire`), и до его слова имени
#: тут нет вовсе: молчаливой подделки у службы раздач не бывает.
_reserve_engines: TorrentEngines


def _configure_cache_reserve(engines: TorrentEngines) -> None:
    """Назначить, чем сценарий берёт службу раздач."""
    global _reserve_engines
    _reserve_engines = engines


def _cache_reserve(config: Config, entry: Entry) -> str:
    """Сколько минут показа лежит в кэше службы прямо сейчас, языком зрителя.

    Число считается из того, что уже есть: набитое в кэше спрашивает сама служба
    (:meth:`torrcast.ports.torrent_engine.TorrentEngine.cache`), битрейт лежит в записи
    (:attr:`Entry.vbps`). Спросить - один запрос к местной службе, и только из ``cast
    status``: горячий путь показа сюда не ходит.

    Минуты - частное от битрейта ЭТОГО файла, а не константа: замер показал, что одни
    и те же гигабайты кэша - это 32 минуты тяжёлого релиза и вдвое больше лёгкого.
    Звук источника в записи не хранится и потому не учитывается - оценка чуть щедрая,
    и число читается как «примерно столько».

    Любое звено может умереть, и каждая смерть - честная строка, а не исключение и не
    молчание: нет хэша раздачи (запись прежней версии) - спросить нечего и строки нет,
    служба не отвечает или молчит про кэш - «неизвестно», битрейт не спрошен - минуты
    не перевести, кэш пуст - запаса нет.
    """
    if not entry.torrent:
        return ""
    try:
        payload = _reserve_engines(config.torrserver_url, timeout=PROBE_TIMEOUT).cache(
            entry.torrent
        )
    except InfraError:
        return "запас в кэше службы неизвестен - служба раздач не отвечает"
    filled = payload.get("Filled")
    if not isinstance(filled, int) or isinstance(filled, bool) or filled < 0:
        return "запас в кэше службы неизвестен - служба про него молчит"
    if filled == 0:
        return "кэш службы пуст, запаса показа в нём нет"
    if entry.vbps <= 0:
        return "запас в кэше службы есть, в минуты не перевести - битрейт файла неизвестен"
    minutes = filled * 8 / (entry.vbps * 1e6 * 60)
    if minutes < 1:
        return "в кэше службы запас меньше минуты показа"
    return f"в кэше службы запас ещё на {minutes:.0f} мин показа"
