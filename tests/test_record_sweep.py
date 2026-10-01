"""Раздачи истории за первыми записями ряда сносятся из базы TorrServer вместе с кэшем."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import pytest

from torrcast.domain.continue_row import WARM_ROW
from torrcast.domain.entry import Entry
from torrcast.domain.torrent_hash import _torrent_hash
from torrcast.usecases.torrent_claims import CLAIMS
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

    def add(self, magnet: str) -> str:
        self.listed.add(_torrent_hash(magnet))
        return _torrent_hash(magnet)


def test_releases_of_records_beyond_the_first_are_removed() -> None:
    foreign = "f" * 40  # раздача поиска или показа, не из истории
    base = _Base({_hash(n) for n in range(WARM_ROW + 2)} | {foreign})

    gone, whole = record_sweep(base, _entries(WARM_ROW + 2), lambda h: False)

    assert gone == base.dropped == [_hash(WARM_ROW), _hash(WARM_ROW + 1)]
    assert whole
    assert base.listed == {_hash(n) for n in range(WARM_ROW)} | {foreign}


def test_a_release_in_use_is_spared() -> None:
    base = _Base({_hash(n) for n in range(WARM_ROW + 2)})

    record_sweep(base, _entries(WARM_ROW + 2), lambda h: h == _hash(WARM_ROW))

    assert base.dropped == [_hash(WARM_ROW + 1)]


def test_a_release_the_service_does_not_have_is_not_removed() -> None:
    base = _Base({_hash(0)})

    assert record_sweep(base, _entries(WARM_ROW + 2), lambda h: False) == ([], True)
    assert base.dropped == []


def test_a_watched_record_leaves_the_row_and_its_release_goes() -> None:
    entries = _entries(WARM_ROW + 1)
    entries["k0"].pos = entries["k0"].dur
    base = _Base({_hash(n) for n in range(WARM_ROW + 1)})

    record_sweep(base, entries, lambda h: False)

    assert base.dropped == [_hash(0)]


def test_a_record_with_a_base32_magnet_is_swept_by_its_hex() -> None:
    """Без перевода в hex такая запись не убиралась, и её кэш лежал в службе вечно."""
    entries = _entries(WARM_ROW + 1)
    entries[f"k{WARM_ROW}"].magnet = "magnet:?xt=urn:btih:AAAQEAYEAUDAOCAJBIFQYDIOB4IBCEQT&dn=x"
    hexed = "000102030405060708090a0b0c0d0e0f10111213"
    base = _Base({_hash(n) for n in range(WARM_ROW)} | {hexed})

    assert record_sweep(base, entries, lambda h: False) == ([hexed], True)


class _Holder:
    """Держатель записи, заводящий её раздачу (:meth:`TorrentClaims.adding`)."""


@pytest.mark.machine
def test_a_release_taken_between_the_check_and_the_drop_survives() -> None:
    """🔴 Гонка уборки на старте: держатель заводил плитку между проверкой и сносом.

    Снос выдёргивал заведённую раздачу, держатель ждал её метаданных впустую и глушил
    плитку на пять минут. Под замком отметок держатель заводит её после сноса заново.
    """
    late = _hash(WARM_ROW)
    base, holder = _Base({_hash(n) for n in range(WARM_ROW + 1)}), _Holder()
    magnet = f"magnet:?xt=urn:btih:{late}&dn=film"
    took = threading.Thread(target=CLAIMS.adding, args=(magnet, holder, base.add))

    def checked(torrent_hash: str) -> bool:
        took.start()  # держатель пришёл сразу после проверки «ничья ли»
        took.join(0.3)
        return False

    try:
        record_sweep(base, _entries(WARM_ROW + 1), checked)
        took.join(3)
        assert late in base.listed, "снос выдернул раздачу из-под держателя"
    finally:
        CLAIMS.unclaim(late, holder)


#: Сетевой ``rem`` медленной или глухой службы; живьём он 0.006-0.08 с.
SLOW = 0.4


@dataclass
class _Stuck(_Base):
    """Служба отвечает на список, а на ``rem`` тянет; ``answer`` - принят ли снос в итоге."""

    answer: bool = False
    began: threading.Event = field(default_factory=threading.Event)

    def drop(self, torrent_hash: str) -> bool:
        self.began.set()
        time.sleep(SLOW)
        return self.answer and super().drop(torrent_hash)


@pytest.mark.machine
@pytest.mark.parametrize("answer", [False, True], ids=["deaf", "slow"])
def test_an_add_waits_for_one_drop_not_for_the_whole_sweep(answer: bool) -> None:
    """🔴 Сетевой ``rem`` идёт под замком отметок, и заводящий раздачу ждал все сносы прохода.

    Синтетика 01-10-2026: четыре раздачи за рядом и ``rem`` по 5 с держали «Играть» 19 с,
    глухой ``rem`` - 39 с. Замок не честный: уборка перехватывала его между сносами.
    """
    base, holder, ff = (
        _Stuck({_hash(n) for n in range(WARM_ROW + 4)}, answer=answer),
        _Holder(),
        "f" * 40,
    )
    sweep = threading.Thread(
        target=record_sweep, args=(base, _entries(WARM_ROW + 4), lambda h: False)
    )
    sweep.start()
    assert base.began.wait(3)
    asked = time.monotonic()
    try:
        CLAIMS.adding(f"magnet:?xt=urn:btih:{ff}", holder, lambda magnet: ff)
        waited = time.monotonic() - asked
    finally:
        CLAIMS.unclaim(ff, holder)
    sweep.join(10)

    assert waited < SLOW + 0.25, f"заводящий ждал {waited:.2f} с при сносе {SLOW} с"
