"""Запасной ход кончившейся очереди: лучший из слабых роёв, но только живой."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import torrcast.usecases.select_bench._bench_state as _bench_state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.select_bench._bench_supply import _supply_note

if TYPE_CHECKING:
    from torrcast.domain.profile import Profile
    from torrcast.ports.torrent_engine import TorrentEngine
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select_bench._bench_tally import _Tally

#: Слабый рой очереди: отношение, скорость и нужда в Мбит/с и сам прогрев.
Weak = tuple[float, float, float, "_Prep"]


def _weak_alive(
    profile: Profile,
    torrserver: TorrentEngine,
    weak: Weak,
    tally: _Tally,
    forget: Callable[[_Prep], None],
) -> _Prep | None:
    """Слабый рой, который ещё можно показать, или ``None`` - он не довезёт кадра.

    🔴 TC-1291. Очередь кончилась, годного нет, и раньше брался лучший из слабых при
    ЛЮБОМ отношении - вплоть до «беру (0.00x)». Ноль на вехах прогрева при этом не
    приговор: ffprobe читает голову, уже лежащую в кэше, и в окне замера рою нечего
    отдавать, а рой, который DHT ещё не раскачал, к концу очереди мог ожить. Поэтому
    рой ниже пола (:attr:`Profile.supply_floor`) перемеряется под настоящим спросом -
    серединой файла, которой не читал никто (:func:`swarm_demand`), - и судит новое
    число. Живой берётся с ним, мёртвый не берётся: обход идёт дальше тем же путём,
    что и без слабого роя, - к запасному безрусскому ходу, перепросу или отказу.
    """
    ratio, got, need, prep = weak
    if ratio < profile.supply_floor and prep.video is not None and need > 0:
        source = torrserver.stream_url(prep.torrent_hash, prep.video.index)
        speed = _bench_state._bench_swarm_demand(
            source, prep.video.size // 2, profile.supply_demand_seconds
        )
        got = speed * 8 / 1_000_000
        ratio = got / need
    numbers = {"got": f"{got:.2f}", "need": f"{need:.2f}", "ratio": f"{ratio:.2f}"}
    if ratio < profile.supply_floor:
        why = phrase("select_bench.reason_thin_swarm", **numbers)
        tally.judged[prep.number] = why
        tally.tried = [
            f"{prep.number} - {why}" if line.startswith(f"{prep.number} - ") else line
            for line in tally.tried
        ]
        print(phrase("select_bench.weak_dead", number=prep.number, **numbers))
        forget(prep)
        return None
    tally.judged.pop(prep.number, None)
    print(_supply_note(prep, got, need, ratio))
    return prep
