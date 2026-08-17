"""Сырая выдача каталога раздач: пакет и есть её порт для композиционного корня.

Склейка и разбор строк - это весь :class:`~torrcast.ports.torrent_catalogue.
TorrentCatalogue`, и отдельного объекта под него заводить незачем: корень
(:mod:`torrcast.runtime.wire`) отдаёт сценариям поиска сам пакет.
"""

from torrcast.adapters.prowlarr.merge import merge as merge
from torrcast.adapters.prowlarr.to_releases import to_releases as to_releases

__all__ = ["merge", "to_releases"]
