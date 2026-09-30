"""Раздачи истории за первыми записями ряда сносятся из базы TorrServer вместе с кэшем."""

from __future__ import annotations

from dataclasses import dataclass, field

from torrcast.domain.continue_row import WARM_ROW
from torrcast.domain.entry import Entry
from web.record_sweep import record_sweep


def _hash(n: int) -> str:
    return f"{n:040x}"


def _entries(count: int) -> dict[str, Entry]:
    """Записи ``k0``..: ``k0`` свежая, у каждой свой магнит с точным хэшем."""
    return {
        f"k{n}": Entry(
            title=f"Фильм {n}",
            magnet=f"magnet:?xt=urn:btih:{_hash(n)}&dn=film",
            pos=60.0,
            dur=6000.0,
            updated=f"2026-01-{30 - n:02d}",
        )
        for n in range(count)
    }


@dataclass
class _Base:
    """База службы: что в ней лежит и что из неё снесли."""

    listed: set[str]
    dropped: list[str] = field(default_factory=list)

    def hashes(self) -> set[str]:
        return set(self.listed)

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)
        self.listed.discard(torrent_hash)
        return True


def test_releases_of_records_beyond_the_first_are_removed() -> None:
    foreign = "f" * 40  # раздача поиска или показа, не из истории
    base = _Base({_hash(n) for n in range(WARM_ROW + 2)} | {foreign})

    gone = record_sweep(base, _entries(WARM_ROW + 2), lambda h: False)

    assert gone == base.dropped == [_hash(WARM_ROW), _hash(WARM_ROW + 1)]
    assert base.listed == {_hash(n) for n in range(WARM_ROW)} | {foreign}


def test_a_release_in_use_is_spared() -> None:
    base = _Base({_hash(n) for n in range(WARM_ROW + 2)})

    record_sweep(base, _entries(WARM_ROW + 2), lambda h: h == _hash(WARM_ROW))

    assert base.dropped == [_hash(WARM_ROW + 1)]


def test_a_release_the_service_does_not_have_is_not_removed() -> None:
    base = _Base({_hash(0)})

    assert record_sweep(base, _entries(WARM_ROW + 2), lambda h: False) == []
    assert base.dropped == []


def test_a_watched_record_leaves_the_row_and_its_release_goes() -> None:
    entries = _entries(WARM_ROW + 1)
    entries["k0"].pos = entries["k0"].dur
    base = _Base({_hash(n) for n in range(WARM_ROW + 1)})

    record_sweep(base, entries, lambda h: False)

    assert base.dropped == [_hash(0)]
