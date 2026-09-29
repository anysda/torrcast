"""Голова с полки: живая упаковка обходит место, которое лежит на полке или его туда кладут."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import factory, feed, lay, packer, tract, vault
from torrcast.usecases.feed_pack.feed_heading import HEAD_WAIT, _awaiting, _heading
from torrcast.usecases.feed_pack.feed_restart import _begin
from torrcast.usecases.warm.head_work import head_work

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Recoder:
    """Кодировщик показа: чьи места ему кодировать незачем и откуда пошла упаковка."""

    spare: Any = None
    done: set[int] = field(default_factory=set)
    heads: list[int] = field(default_factory=list)

    def opening(self, slot: int) -> None:
        self.heads.append(slot)

    def note(self, slot: int, how: str) -> None: ...

    def after_recode(self, slot: int) -> bool:
        return False

    def holding(self, slot: int, size: int) -> bool:
        return False


def _show(tmp_path: Path, **parts: Any) -> Any:
    store = vault(tmp_path)
    return feed(tmp_path, vault=store, recoder=_Recoder(), **parts)


def test_a_plain_start_packs_its_own_first_place(tmp_path: Path, journal: Path) -> None:
    """Полка пуста и головы не кладут: упаковка начинается там же, где показ."""
    tract(now=100.0)
    show = _show(tmp_path)

    assert _heading(show, 0) == 0
    assert show.recoder.done == set()


def test_a_head_already_on_the_shelf_is_not_packed_or_coded_again(
    tmp_path: Path, journal: Path
) -> None:
    """Голова легла с карточки: упаковка идёт со второго места, кодировщик её не трогает."""
    tract(now=100.0)
    show = _show(tmp_path)
    lay(show.vault.dir, 0)

    assert _heading(show, 0) == 1
    assert show.recoder.done == {0}, "кодировщик показа кодирует голову с полки второй раз"
    assert show.heading == (-1, 0.0), "лежащую голову ждут как ещё не лёгшую"


def test_a_head_being_laid_is_awaited_not_packed(tmp_path: Path, journal: Path) -> None:
    """Голову ещё кладут: упаковка идёт со второго места, а запрос головы её ждёт."""
    clock = tract(now=100.0)
    show = _show(tmp_path)
    head_work(show.vault.dir, 0).mkdir()

    assert _heading(show, 0) == 1
    assert show.heading == (0, 100.0)
    assert _awaiting(show, 0) is True
    assert _awaiting(show, 1) is False, "ждут не то место"

    clock.now += HEAD_WAIT
    assert _awaiting(show, 0) is False, "брошенный знак головы держит показ вечно"
    assert show.recoder.done == set(), "не лёгшую голову кодировщик так и не возьмёт"


def test_a_head_that_did_not_land_is_packed_by_the_show(tmp_path: Path, journal: Path) -> None:
    """Заход головы кончился, а куска нет: место снова обычное, его пакуют и кодируют."""
    tract(now=100.0)
    show = _show(tmp_path)
    head_work(show.vault.dir, 0).mkdir()
    _heading(show, 0)
    head_work(show.vault.dir, 0).rmdir()

    assert _awaiting(show, 0) is False
    assert show.recoder.done == set()


def test_a_head_landing_under_the_steer_is_still_awaited(tmp_path: Path, journal: Path) -> None:
    """Голова легла между взглядом на полку и решением: перепаковывать её уже незачем."""
    tract(now=100.0)
    show = _show(tmp_path)
    head_work(show.vault.dir, 0).mkdir()
    _heading(show, 0)
    head_work(show.vault.dir, 0).rmdir()
    lay(show.vault.dir, 0)

    assert _awaiting(show, 0) is True
    assert show.recoder.done == {0}


def test_the_last_place_is_packed_even_from_the_shelf(tmp_path: Path, journal: Path) -> None:
    """За последним местом паковать нечего: обходить его не с чем."""
    tract(now=100.0)
    show = _show(tmp_path)
    lay(show.vault.dir, 5)

    assert _heading(show, 5) == 5


def _begun(tmp_path: Path, laying: bool) -> tuple[Any, list[int]]:
    """Начать показ с нуля, когда голова лежит на полке или её туда кладут."""
    started: list[int] = []

    def _start(command: list[str], out: Path, run: Path, first: int, **kwargs: Any) -> Any:
        started.append(first)
        run.mkdir(parents=True, exist_ok=True)
        return packer(out.parent, out=out, run=run, first=first)

    tract(
        now=100.0,
        settle_start=lambda _source, want: (want, want),
        pack_command=lambda *a, **k: ["ffmpeg"],
        packer=factory(_start),
    )
    show = _show(tmp_path)
    if laying:
        head_work(show.vault.dir, 0).mkdir()
    else:
        lay(show.vault.dir, 0)
    assert _begin(show, 0.0, lambda slot, size: False) == 0.0
    return show, started


def test_the_show_start_packs_past_the_head_on_the_shelf(tmp_path: Path, journal: Path) -> None:
    """Начало показа: и упаковка, и голова кодировщика встают за головой с полки."""
    show, started = _begun(tmp_path, laying=False)

    assert started == [1], "упаковка показа пакует голову, которая лежит на полке"
    assert show.recoder.heads == [1]


def test_a_head_being_laid_stays_promised_by_the_playlist(tmp_path: Path, journal: Path) -> None:
    """Голову ещё кладут: манифест её обещает, иначе приёмник начнёт со второго места."""
    show, started = _begun(tmp_path, laying=True)

    assert started == [1]
    assert 0 not in show._gaps(), "манифест не обещает голову, которую вот-вот положат"
