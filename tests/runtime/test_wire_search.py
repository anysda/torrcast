"""Проводка поиска и отбора: после неё в слотах стоят настоящий каталог и служба раздач."""

from __future__ import annotations

import torrcast.usecases.discover._search_state as _search_state
import torrcast.usecases.torrents as torrents
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.runtime.wire_search import wire_search


def test_the_search_gets_the_real_catalogue_and_the_real_release_service() -> None:
    """Завод клиента индексеров и служба раздач в слотах - те самые, а не однофамильцы.

    Живое приложение проводит поиск на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слоты берут своё значение отсюда.
    """
    wire_search()

    assert _search_state._search_indexers is Prowlarr
    assert _search_state._search_catalogue is torrent_catalogue
    assert torrents._cleanup_engines is TorrServer
