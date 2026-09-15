"""Внешний мир поиска: каталог раздач, справка о картинах и завод клиента индексеров."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.proof_in_map import KnownPictures
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
#: Картины офлайн-карты IMDb под прокатным именем: ими разбор выдачи доказывает картину
#: запроса и меряет её известность против соседей по слову
#: (:func:`~torrcast.usecases.discover.franchise_pick.franchise_pick`).
_search_known: KnownPictures


def _unrecognized(_query: str, _wait: float) -> MapPicture | None:
    return None


#: Which picture of the offline map the query names, waiting up to the given seconds for a
#: cold map: the first round then asks the indexers by its names too
#: (:mod:`torrcast.usecases.discover.named_round`). Without a map nothing is recognized.
_search_recognize: Callable[[str, float], MapPicture | None] = _unrecognized


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


def _configure_known(known: KnownPictures) -> None:
    """Передать поиску офлайн-карту картин: читается она лишь тогда, когда тёзки спорят."""
    global _search_known
    _search_known = known


def _configure_recognize(recognize: Callable[[str, float], MapPicture | None]) -> None:
    """Give the search the offline map's recognizer of a picture by its name."""
    global _search_recognize
    _search_recognize = recognize
