"""Внешний мир поиска: каталог раздач, справка о картинах и завод клиента индексеров."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.passport_source import PassportSource
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue

#: Каталог раздач, справка о картинах и завод клиента индексеров - всё, что у поиска
#: снаружи. Кладёт это композиционный корень (:mod:`torrcast.runtime.wire`): и сырая
#: выдача, и статья справки приезжают из сети, а слою сценариев сеть не назвать.
#:
#: ⚠️ Имена длиннее очевидных нарочно - ровно по той же причине, что и у добора
#: (:mod:`torrcast.usecases.reinforce`): плоский namespace прежнего монолита
#: (:mod:`torrcast.cli`) вписывает в КАЖДУЮ свою часть globals всех остальных, и короткое
#: имя тут же затирается чужой одноимённой функцией.
_search_catalogue: TorrentCatalogue
_search_passport: PassportSource
_search_indexers: Callable[[str, str], IndexerClient]


def _configure_discover(
    catalogue: TorrentCatalogue,
    passport: PassportSource,
    indexers: Callable[[str, str], IndexerClient],
) -> None:
    """Передать поиску каталог раздач, справку о картинах и завод клиента индексеров."""
    global _search_catalogue, _search_passport, _search_indexers
    _search_catalogue = catalogue
    _search_passport = passport
    _search_indexers = indexers
