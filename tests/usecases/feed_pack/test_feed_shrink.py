"""Тяжёлый кусок на последнем гейте: ужать на месте или честно пропустить место."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from tests.fakes.journal import Tape
from tests.usecases.feed_pack.world import factory, feed, grid, lay, packer, tract
from torrcast.adapters.filesystem.trace_journal.file_journal import FileJournal
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.encode_settings import MAXRATE_GAIN
from torrcast.adapters.recode.pace import Pace
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.packer_publish import _lay_out
from torrcast.domain.delivered_mbit import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.digest._session_block import _session_block
from torrcast.domain.hls_settings import MAX_SEGMENT_BYTES
from torrcast.domain.segment_container import FMP4
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.shrunk_splice_events import (
    SHRUNK,
    SHRUNK_SPLICE_ATTEMPT,
    SHRUNK_SPLICE_NOT_TRIED,
)
from torrcast.ports.journal import slot as journal_slot
from torrcast.usecases.feed_pack.feed_shrink import _shrink, _skip

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class _Encode:
    mbit: float = 4.0


@dataclass
class _Pace:
    def table(self) -> list[tuple[str, float]]:
        return [("veryfast", 1.0), ("ultrafast", 2.0)]


@dataclass
class _Recoder:
    """Кодировщик тяжёлых кусков под рукой зеркала: перекода нет, есть только ответы."""

    spare: Path
    over_wait: float = 5.0
    fits: bool = False
    size: int = 5
    done: set[int] = field(default_factory=set)
    pace: _Pace = field(default_factory=_Pace)

    def fit(self, span: float, preset: str) -> _Encode:
        return _Encode()

    def ready(self, slot: int) -> Path | None:
        path = self.spare / f"v{slot}.ts"
        return path if self.fits and path.exists() else None


def _tract(laid: list[int], start: Any = None) -> None:
    """Собрать ужатию стендовый медиатракт: ffmpeg не поднимается ни разу."""

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        laid.append(first)
        run.mkdir(parents=True, exist_ok=True)
        return packer(run.parent, out=out, run=run, first=first, edge=first)

    tract(pack_command=lambda *a, **k: ["ffmpeg"], packer=factory(start or _start))


def _recoder(tmp_path: Path, **kwargs: Any) -> _Recoder:
    spare = tmp_path / "recode"
    spare.mkdir(parents=True, exist_ok=True)
    return _Recoder(spare=spare, **kwargs)


def test_a_decision_about_a_place_is_taken_once_and_said_once(tmp_path: Path) -> None:
    """Место уже пропущено - второй раз ни ужимать, ни говорить о нём не надо."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append)
    show.skipped.add(4)

    assert _shrink(show, 4, 20_000_000) is False and said == []


def test_without_an_encoder_the_place_is_honestly_skipped_and_named(
    tmp_path: Path, journal: Path
) -> None:
    """Ужимать нечем - место пропускается вслух: приёмнику про пропуск отвечает показ."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append)

    assert _shrink(show, 4, 20_000_000) is False
    assert show.skipped == {4}
    weight = phrase("feed.weight_mb", mb=20)
    reason = phrase("feed.shrink_reason_none")
    assert said == [phrase("feed.skip_heavy", slot=4, weight=weight, reason=reason)]


def test_on_a_whole_film_recode_a_side_run_is_forbidden(tmp_path: Path, journal: Path) -> None:
    """Чужой заход в середину сплошного перекода - это смена SPS на ходу, её ТВ не переживёт."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append, recoder=_recoder(tmp_path), encode=object())

    assert _shrink(show, 4, 0) is False
    assert said and phrase("feed.shrink_reason_forbidden") in said[0]
    assert phrase("feed.weight_mb", mb=0) not in said[0], "вес не измерен - строку не выдумываем"


def test_a_recode_that_arrived_while_we_waited_for_the_lock_is_taken_as_is(tmp_path: Path) -> None:
    """Пока ждали замок, перекод доехал сам - поднимать ради него ещё один ffmpeg незачем."""
    laid: list[int] = []
    _tract(laid)
    recoder = _recoder(tmp_path, fits=True)
    lay(recoder.spare, 4, size=5)
    show = feed(tmp_path, recoder=recoder, cap=100)

    assert _shrink(show, 4, 20_000_000) is None
    assert laid == [] and show.skipped == set()


def test_a_shrunk_piece_that_fits_the_ceiling_saves_the_place(
    tmp_path: Path, journal: Path
) -> None:
    """Ужатие - один короткий прогон ровно на этот сегмент; влез - место спасено."""
    laid: list[int] = []
    said: list[str] = []
    _tract(laid)
    recoder = _recoder(tmp_path)
    show = feed(tmp_path, recoder=recoder, log=said.append, cap=100, grid=grid(60.0, 10.0))

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        laid.append(first)
        run.mkdir(parents=True, exist_ok=True)
        lay(recoder.spare, first, size=50)
        recoder.fits = True
        return packer(run.parent, out=out, run=run, first=first, edge=first)

    _tract(laid, start=_start)

    assert _shrink(show, 4, 20_000_000) is True
    assert laid == [4] and show.skipped == set()
    weight = phrase("feed.weight_mb", mb=20)
    assert said == [phrase("feed.shrinking", slot=4, weight=weight, mbit=4.0)]


def test_a_shrink_that_did_not_fit_is_a_skip_and_not_a_second_try(
    tmp_path: Path, journal: Path
) -> None:
    """Ужать не вышло - место пропускается: стоять на нём значит крутить круг вечно."""
    said: list[str] = []
    _tract([])
    show = feed(tmp_path, recoder=_recoder(tmp_path), log=said.append, grid=grid(60.0, 10.0))

    assert _shrink(show, 4, 20_000_000) is False
    assert show.skipped == {4}
    assert any(phrase("feed.shrink_reason_failed") in line for line in said)


def test_a_failed_shrink_closes_the_splice_arithmetic_on_the_product_tape(
    tmp_path: Path, tape: Tape
) -> None:
    """Ужатие без вызова склейки попадает в «без попытки» из настоящего пути продукта."""
    _tract([])
    show = feed(tmp_path, recoder=_recoder(tmp_path), grid=grid(60.0, 10.0))

    assert _shrink(show, 4, 20_000_000) is False
    rows = [
        {"at": 0.0, "sid": "s", "phase": "timeline", "event": event, **facts}
        for event, facts in tape.calls
    ]

    assert "shrinks 1, shrunk splice: attempts 0, wins 0, not tried 1" in _session_block("s", rows)


def test_every_product_shrink_has_a_splice_decision_on_the_file_tape(
    tmp_path: Path, journal: Path
) -> None:
    """Попытки и отказы от склейки сходятся со всеми настоящими ужатиями на ленте."""
    file_journal = FileJournal()
    journal_slot.install(file_journal)

    recoder = _recoder(tmp_path / "shrunk")
    show = feed(tmp_path / "shrunk", recoder=recoder, cap=100, grid=grid(60.0, 10.0))

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        run.mkdir(parents=True, exist_ok=True)
        lay(recoder.spare, first, size=50)
        recoder.fits = True
        return packer(run.parent, out=out, run=run, first=first, edge=first)

    _tract([], start=_start)
    first = packer(tmp_path / "first", spare=recoder.spare, cap=100, shrink=show._shrink)
    lay(first.run, 4, size=200)
    _lay_out(first, lambda: True, merge=lambda *a, **k: _merged(a[2], 50))

    arrived = _recoder(tmp_path / "arrived")
    later = feed(tmp_path / "arrived", recoder=arrived, cap=100, grid=grid(60.0, 10.0))

    def _arrive(slot: int, size: int) -> bool | None:
        lay(arrived.spare, slot, size=50)
        arrived.fits = True
        return later._shrink(slot, size)

    second = packer(tmp_path / "second", spare=arrived.spare, cap=100, shrink=_arrive)
    lay(second.run, 5, size=200)
    _lay_out(second, lambda: True, merge=lambda *a, **k: _merged(a[2], 50))

    file_journal.shutdown()
    rows = file_journal.records()
    shrinks = sum(row.get("event") == SHRUNK for row in rows)
    attempts = sum(row.get("event") == SHRUNK_SPLICE_ATTEMPT for row in rows)
    not_tried = sum(str(row.get("event", "")).startswith(SHRUNK_SPLICE_NOT_TRIED) for row in rows)
    summary = _session_block("test-sid", rows).splitlines()[-1].strip()

    assert attempts + not_tried == shrinks, summary


def _merged(path: Path, size: int) -> bool:
    path.write_bytes(b"m" * size)
    return True


def test_a_shrink_that_gave_no_bytes_at_all_is_not_a_verdict_about_the_piece(
    tmp_path: Path, journal: Path
) -> None:
    """🔴 TC-725. Ни одного байта - это отказ ИСТОЧНИКА, а не приговор куску.

    Живой замер: службу раздач убили на 70-й минуте показа, перекод и ужатие подряд
    ответили «Connection refused», и два места по десять секунд ушли в приговор
    навсегда. Служба вернулась через пять секунд, а дыра в фильме осталась.
    """
    _tract([])
    show = feed(tmp_path, recoder=_recoder(tmp_path), grid=grid(60.0, 10.0))

    assert _shrink(show, 4, 20_000_000) is False
    assert show.skipped == {4} and show.doubted == {4}, "приговор вынесен окончательным"


def test_a_piece_that_was_shrunk_and_still_did_not_fit_is_judged_for_good(
    tmp_path: Path, journal: Path
) -> None:
    """Ужалось и всё равно не влезло - кусок детерминирован, и второй заход даст то же."""
    recoder = _recoder(tmp_path)
    show = feed(tmp_path, recoder=recoder, cap=100, grid=grid(60.0, 10.0))

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        run.mkdir(parents=True, exist_ok=True)
        lay(recoder.spare, first, size=5_000)  # ужалось, но потолка не одолело
        recoder.fits = True
        return packer(run.parent, out=out, run=run, first=first, edge=first)

    _tract([], start=_start)

    assert _shrink(show, 4, 20_000_000) is False
    assert show.skipped == {4} and show.doubted == set(), "приговор объявлен условным"


def test_a_skipped_place_is_taken_off_the_encoders_list_too(tmp_path: Path, journal: Path) -> None:
    """Кодировщику за пропущенное место браться уже незачем: копия там детерминирована."""
    recoder = _recoder(tmp_path)
    show = feed(tmp_path, recoder=recoder)

    assert _skip(show, 7, 0, "ужимать нечем") is False
    assert show.skipped == {7} and recoder.done == {7}


def test_the_spot_shrink_aims_under_both_ceilings_of_the_receiver(tmp_path: Path) -> None:
    """🔴 TC-495: у приёмника ДВА потолка, а ужатие считало цель по одному - по весу.

    Живой показ 11-08 (сеанс на Q70D): ужатие сработало на слотах 0, 2 и 4, попросив
    8.87, 7.32 и 9.00 Мбит/с, а наружу уехало 9.65, 8.33 и **10.94** Мбит/с при потолке
    битрейта около десяти. Четыре подгруза в первую минуту, и ранние места ровно эти.
    Кусок был короткий, поэтому по весу влезал с запасом: чем короче кусок, тем больше
    мегабит в секунду помещается в одни и те же 16 МБ.

    Сам ffmpeg тут не нужен и не зовётся: проверяется РЕШЕНИЕ, а оно принимается и
    называется вслух до всякого прогона - потому заводу прогона тут и разрешено падать.
    """

    class _Ceilings:
        """Кодировщик-заглушка: ровно то, что спрашивает ужатие, и оба потолка при нём."""

        def __init__(self, spare: Path) -> None:
            self.spare = spare
            self.encode = Encode()
            self.pace = Pace()
            self.threshold = 10.0  # потолок битрейта приёмника, ``recode_at_mbit``
            self.cap = MAX_SEGMENT_BYTES  # потолок веса, тот же, которым меряет показ
            self.over_wait = 60.0
            self.done: set[int] = set()
            self.played = 0.0

        def stop(self) -> None: ...

        def opening(self, slot: int) -> None: ...

        def note(self, slot: int, how: str) -> None: ...

        def holding(self, slot: int, size: int = 0) -> bool:
            return False

        def ready(self, slot: int) -> Path | None:
            return None

        def fit(self, span: float, preset: str) -> Encode:
            # Тело - копия :meth:`torrcast.adapters.recode.recoder.Recoder.fit`, знак в знак:
            # заглушка со своим расчётом зелена при любом контракте.
            return replace(self.encode, preset=preset).fit(span, self.cap, self.threshold)

    def _dead(*args: Any, **kwargs: Any) -> Any:
        raise OSError("ffmpeg не поднялся - для решения это неважно")

    said: list[str] = []
    tract(packer=factory(_dead))
    recoder = _Ceilings(tmp_path / "recode")
    # Тот самый слот 4 того самого сеанса: 9.55 с фильма.
    show = feed(
        tmp_path,
        grid=Grid(bounds=(0.0, 9.55), duration=19.1),
        log=said.append,
        recoder=recoder,
    )

    assert _shrink(show, 0, MAX_SEGMENT_BYTES + 1) is False
    # Мбит/с всегда с дробной частью, а вес куска - целым числом: дробное число в
    # строке единственное, и это оно, независимо от слов языка вокруг него.
    found = re.search(r"\d+\.\d+", said[0])
    assert found is not None
    asked = float(found.group())
    went = (asked * MAXRATE_GAIN + AUDIO_MBIT) * TS_OVERHEAD
    assert went <= recoder.threshold, "ужатие обязано укладываться в потолок битрейта"
    assert went * 9.55 / 8 <= show.cap / 1e6, "и в потолок веса оно укладываться не перестало"


def test_the_shrink_run_cuts_in_the_container_the_receiver_asked_for(tmp_path: Path) -> None:
    """Ужатие - такой же прогон упаковки, и режет он тем же контейнером, что и показ.

    Резать своим - значит положить готовый кусок под чужим именем: выкладка его не
    находит, место не выходит наружу никогда, а запрос приёмника крутит перепаковку.
    """
    seen: list[dict[str, Any]] = []

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        seen.append(kwargs)
        run.mkdir(parents=True, exist_ok=True)
        return packer(run.parent, out=out, run=run, first=first, edge=first)

    made: list[dict[str, Any]] = []

    def _command(*args: Any, **kwargs: Any) -> list[str]:
        made.append(kwargs)
        return ["ffmpeg"]

    tract(pack_command=_command, packer=factory(_start))
    show = feed(tmp_path, grid=grid(), recoder=_Recoder(spare=tmp_path / "recode"), cap=1)
    show.container = FMP4

    _shrink(show, 3, size=MAX_SEGMENT_BYTES)

    assert made[0]["container"] == FMP4, "команда ужатия обязана резать контейнером показа"
    assert seen[0]["container"] == FMP4, "и прогон обязан знать тот же контейнер"
