"""Внешний мир команды показа: служба раздач, настройки, справка и разбор выдачи.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) одним словом
(:func:`_configure_cast_command`); читают все части команды.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.ports.torrent_catalogue import RawRow
from torrcast.ports.torrent_engines import TorrentEngines

if TYPE_CHECKING:
    from torrcast.ports.choice_types import Facts


#: Внешний мир команды показа. Всё это кладёт композиционный корень
#: (:mod:`torrcast.runtime.wire`): сценарий знает, ЧТО ему нужно - служба раздач, файл
#: настроек, паспорт приёмника, справка о картинах, происхождение картины, порядок
#: последней таблицы релизов и разбор сырой выдачи каталога, - а КТО за этим стоит, не
#: его дело. До слова корня имён тут нет вовсе: молчаливой подделки у сети не бывает.
#:
#: ⚠️ Имена длиннее очевидных нарочно. Плоский namespace прежнего монолита
#: (:mod:`torrcast.cli`) вписывает в КАЖДУЮ свою часть globals всех остальных, и короткий
#: тёзка молча затирает функцию соседа.
_play_engines: TorrentEngines
_play_settings: Callable[[], Config]
_play_detect: Callable[[Config], Choice]
_play_facts: Callable[[list[tuple[str, int | None]]], Facts]
_play_native: Callable[[Picture, str], None]
_play_pinned: Callable[[str, str, int], str]
_play_merge: Callable[..., list[RawRow]]
_play_releases: Callable[[list[RawRow]], list[Release]]


def _configure_cast_command(
    engines: TorrentEngines,
    settings: Callable[[], Config],
    detect: Callable[[Config], Choice],
    facts: Callable[[list[tuple[str, int | None]]], Facts],
    native: Callable[[Picture, str], None],
    pinned: Callable[[str, str, int], str],
    merge: Callable[..., list[RawRow]],
    releases: Callable[[list[RawRow]], list[Release]],
) -> None:
    """Назначить команде показа её внешний мир."""
    global _play_engines, _play_settings, _play_detect, _play_facts
    global _play_native, _play_pinned, _play_merge, _play_releases
    _play_engines = engines
    _play_settings = settings
    _play_detect = detect
    _play_facts = facts
    _play_native = native
    _play_pinned = pinned
    _play_merge = merge
    _play_releases = releases
