"""Уборка прогрева и свежий прогрев той же раздачи из другого потока не сносят друг друга."""

from __future__ import annotations

import threading

import pytest

import torrcast.usecases.select_bench._bench_core as _bench_core
from tests.usecases.select_bench.world import Torrents, plan, probes, rel
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.torrent_claims import CLAIMS


class _Standing(Torrents):
    """Служба, которая помнит, стоит ли раздача после всех add и drop."""

    def __init__(self) -> None:
        super().__init__()
        self.standing: set[str] = set()
        self.added = threading.Event()

    def add(self, magnet: str) -> str:
        torrent_hash = super().add(magnet)
        self.standing.add(torrent_hash)
        self.added.set()
        return torrent_hash

    def drop(self, torrent_hash: str) -> bool:
        self.standing.discard(torrent_hash)
        return super().drop(torrent_hash)


class _Squeezed:
    """Отметки процесса, у которых между сканом уборки и снятием отметки встаёт свежий прогрев."""

    def __init__(self, squeeze: threading.Thread, added: threading.Event) -> None:
        self.squeeze, self.added, self.started = squeeze, added, False

    def unclaim(self, torrent_hash: str, owner: object) -> bool:
        if not self.started:
            self.started = True
            self.squeeze.start()
            self.added.wait(0.5)  # под замком стенда свежий прогрев сюда не пролезет
        return CLAIMS.unclaim(torrent_hash, owner)

    def __getattr__(self, name: str) -> object:
        return getattr(CLAIMS, name)


@pytest.mark.machine
def test_a_fresh_warmup_of_the_same_release_survives_a_forget_running_alongside(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Свежий прогрев той же раздачи, заведённый в окне уборки, остаётся в службе.

    Карточка и показ заводят прогрев одной раздачи из разных потоков. Уборка старого прогрева
    сканирует живые прогревы, а отметку снимает позже; свежий прогрев, вставший между ними,
    для уборки не существовал, и его раздачу сносили из-под метаданных.
    """
    torrents = _Standing()
    bench = Bench(torrents, prober=probes([]))
    built = plan([rel()])
    old = bench.start(built, 1)
    assert old.ready.wait(2.0)
    torrents.added.clear()
    fresh: list[object] = []
    squeeze = threading.Thread(target=lambda: fresh.append(bench.start(built, 1)))
    monkeypatch.setattr(_bench_core, "CLAIMS", _Squeezed(squeeze, torrents.added))

    bench._forget(old)
    squeeze.join(2.0)

    assert fresh and fresh[0] is not old
    assert bench.live() == fresh
    assert fresh[0].ready.wait(2.0)  # type: ignore[attr-defined]
    assert f"hash-{old.release.magnet}" in torrents.standing
