"""Внешний мир отбора: служба раздач, паспорт потока и свободный ответ человека."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.prober import Prober
from torrcast.ports.torrent_engines import TorrentEngines

#: Внешний мир отбора: чем заводится служба раздач, чем читается паспорт потока и чем
#: спрашивается свободный ответ человека, и чем проверяется, отдаёт ли записанная
#: раздача содержимое. Адрес службы и её сроки знает сам отбор, а КЕМ она заводится -
#: композиционный корень (:mod:`torrcast.runtime.wire`).
_select_engines: TorrentEngines
_select_prober: Prober
_select_ask_line: Callable[..., str]
_select_first_byte: Callable[[str], Callable[[float], bool | None]]


def _configure_select(
    engines: TorrentEngines,
    prober: Prober,
    ask_line: Callable[..., str],
    first_byte: Callable[[str], Callable[[float], bool | None]],
) -> None:
    """Назначить отбору его внешний мир."""
    global _select_engines, _select_prober, _select_ask_line, _select_first_byte
    _select_engines = engines
    _select_prober = prober
    _select_ask_line = ask_line
    _select_first_byte = first_byte
