"""Запасной ход кончившейся очереди: лучший из слабых роёв, но только живой."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

import torrcast.usecases.select_bench._bench_state as _bench_state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.select_bench._bench_supply import _supply_note, _supply_verdict

if TYPE_CHECKING:
    from torrcast.domain.profile import Profile
    from torrcast.domain.torr_file import TorrFile
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
    читаем середину файла, которой не читал никто (:func:`swarm_demand`), и снимаем
    счётчик приёма раздачи до и после, - и судит новое число. Живой берётся с ним,
    мёртвый не берётся: обход идёт дальше тем же путём, что и без слабого роя, - к
    запасному безрусскому ходу, перепросу или отказу.
    """
    ratio, got, need, prep = weak
    if ratio < profile.supply_floor and prep.video is not None and need > 0:
        remeasured = _remeasure(profile, torrserver, prep.torrent_hash, prep.video)
        if remeasured is None:  # замера не было: берётся, как и до перемера, по вехам
            tally.judged.pop(prep.number, None)
            print(_supply_note(prep, got, need, ratio))
            return prep
        got = remeasured
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
        if prep is not tally.mute:
            tally.dead_voice = tally.dead_voice or prep.number
        forget(prep)
        return None
    tally.judged.pop(prep.number, None)
    print(_supply_note(prep, got, need, ratio))
    return prep


def _mute_alive(
    profile: Profile, torrserver: TorrentEngine, tally: _Tally, forget: Callable[[_Prep], None]
) -> _Prep | None:
    """Запасной безрусский ход (:attr:`_Tally.mute`), если его рой довезёт кадр.

    Паспорт без русской дорожки суда роя в обходе не проходит вовсе, и мёртвый рой
    запасного давал тот же вечный PREPARING, что и «беру (0.00x)». Граница та же:
    без замера берётся как и прежде, выше пола берётся, ниже - перемер под спросом.
    """
    mute = tally.mute
    if mute is None:
        return None
    ratio, got, need = _supply_verdict(profile, mute)
    if ratio < 0 or ratio >= profile.supply_floor:
        return mute
    alive = _weak_alive(profile, torrserver, (ratio, got, need, mute), tally, forget)
    if alive is None:
        tally.mute = None
    return alive


def _remeasure(
    profile: Profile, torrserver: TorrentEngine, torrent_hash: str, video: TorrFile
) -> float | None:
    """Мбит/с роя под спросом или ``None`` - счётчик приёма не прочитан, замера не было.

    Отказ сети не приговор: молчание службы до или после спроса, как и счётчик, ушедший
    назад, дали бы и «везёт 0.00 - не беру», и «везёт 10000 - беру (1250x)». Такой рой
    судится, как судился до перемера, по вехам прогрева.
    """
    source = torrserver.stream_url(torrent_hash, video.index)
    seconds = profile.supply_demand_seconds
    before, began = _intake(torrserver, torrent_hash), time.monotonic()
    if before is None:
        return None
    _bench_state._bench_swarm_demand(source, video.size // 2, seconds)
    after = _intake(torrserver, torrent_hash)
    if after is None or after < before:
        return None
    return (after - before) * 8 / 1_000_000 / max(time.monotonic() - began, seconds)


def _intake(torrserver: TorrentEngine, torrent_hash: str) -> float | None:
    """Сколько байт раздача приняла от роя, или ``None`` - служба промолчала."""
    with suppress(Exception):
        read = cast(Any, torrserver).status(torrent_hash).get("bytes_read")
        if isinstance(read, (int, float)) and not isinstance(read, bool):
            return float(read)
    return None
