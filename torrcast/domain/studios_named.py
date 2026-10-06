"""Студии раздачи, записанные в состояние именами, обратно в знакомые студии."""

from __future__ import annotations

from collections.abc import Iterable

from torrcast.domain.studio import STUDIOS, Studio


def studios_named(names: Iterable[str]) -> tuple[Studio, ...]:
    """Знакомые студии (:data:`STUDIOS`) по именам в том же порядке; незнакомое имя выпадает.

    Запись хранит имена (:attr:`torrcast.domain.entry.Entry.studios`), а не студии целиком:
    ступень и вес живут в таблице и правятся там, а не в файле состояния. Порядок несёт
    смысл (:func:`torrcast.domain.track_studio.track_studio`), поэтому он и сохраняется.
    """
    known = {studio.name: studio for studio in STUDIOS.values()}
    return tuple(known[name] for name in names if name in known)
