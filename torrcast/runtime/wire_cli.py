"""The world of the ``cast`` command: the common one, and the map's recognizer of a picture.

The recognizer is the command line's own: the web bridge sets its prefix index before
:func:`~torrcast.runtime.wire.wire` runs, and the common wiring must not replace it.
"""

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.map_recognize import map_recognize
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.wire import wire
from torrcast.usecases.discover._search_state import _configure_recognize


def _recognize(query: str, _wait: float) -> MapPicture | None:
    return map_recognize(FACTS.catalogue.pictures, query)


def wire_cli() -> None:
    """Wire the process, then let the search ask the indexers by the picture's names."""
    wire()
    _configure_recognize(_recognize)


__all__ = ["wire_cli"]
