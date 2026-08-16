"""Запас показа в кэше службы раздач, языком зрителя: минуты, а не гигабайты.
Спрашивает его ``cast status`` через сеанс показа; горячий путь показа сюда не ходит.
"""

# ruff: noqa: F821, F822

from __future__ import annotations

__all__ = [
    "PROBE_TIMEOUT",
    "Config",
    "Entry",
    "InfraError",
    "TorrServer",
    "_cache_reserve",
]

from torrcast.ports.module import module

for _module_name, _names in {
    "torrcast": ("InfraError",),
    "torrcast.state": ("Config", "Entry"),
    "torrcast.stream": ("PROBE_TIMEOUT", "TorrServer"),
}.items():
    _dependency = module(_module_name)
    globals().update({name: getattr(_dependency, name) for name in _names})


def _cache_reserve(config: Config, entry: Entry) -> str:
    """Сколько минут показа лежит в кэше службы прямо сейчас, языком зрителя.

    Число считается из того, что уже есть: набитое в кэше спрашивает сама служба
    (:meth:`TorrServer.cache`), битрейт лежит в записи (:attr:`Entry.vbps`). Спросить
    - один запрос к местной службе, и только из ``cast status``: горячий путь показа
    сюда не ходит.

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
        payload = TorrServer(config.torrserver_url, timeout=PROBE_TIMEOUT).cache(entry.torrent)
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
