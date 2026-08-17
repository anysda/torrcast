"""Совместимый фасад добора кандидатов.

Заодно это его точка связывания: каталог раздач (:mod:`torrcast.search`) и справка о
картинах (:mod:`torrcast.facts`) по слоям ещё не разложены, и назвать их вправе только
модуль вне слоёв. Сценарий видит их через порты
(:class:`~torrcast.ports.torrent_catalogue.TorrentCatalogue`,
:class:`~torrcast.ports.passport_source.PassportSource`) и о том, кто за ними стоит,
не знает.
"""

import sys

from torrcast import search
from torrcast.facts import origin
from torrcast.usecases import reinforce as _implementation
from torrcast.usecases.reinforce import *  # noqa: F403

__all__ = _implementation.__all__

_implementation.configure(search, origin)

sys.modules[__name__] = _implementation
