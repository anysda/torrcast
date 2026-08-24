"""Каталог раздач одним предметом: склейка выдач и разбор строк в релизы.

Договор стоит в порту
(:class:`torrcast.ports.torrent_catalogue.torrent_catalogue.TorrentCatalogue`), а считают обе
операции соседи по пакету - :func:`torrcast.adapters.prowlarr.merge.merge` и
:func:`torrcast.adapters.prowlarr.to_releases.to_releases`. Предмет нужен потому, что порт
спрашивает ОБЕ операции у одного объекта: раньше этим объектом был сам пакет, и договор держался на
том, что его ``__init__`` раздавал имена соседей. Теперь у предмета свой файл, а имена берутся из
своих домов.
"""

from __future__ import annotations

from torrcast.adapters.prowlarr.merge import merge as _merge
from torrcast.adapters.prowlarr.to_releases import to_releases as _to_releases
from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release


class _ProwlarrCatalogue:
    """Сырая выдача Prowlarr: склеить несколько заходов и разобрать в релизы."""

    @staticmethod
    def merge(*batches: list[RawResult]) -> list[RawResult]:
        """Склеить выдачи нескольких запросов, оставив каждую раздачу один раз."""
        return _merge(*batches)

    @staticmethod
    def to_releases(rows: list[RawResult]) -> list[Release]:
        """Разобрать сырые строки в релизы: имя, размер, сиды, magnet."""
        return _to_releases(rows)


#: Каталог раздач, который композиционный корень ставит в слоты поиска и добора.
torrent_catalogue = _ProwlarrCatalogue()
