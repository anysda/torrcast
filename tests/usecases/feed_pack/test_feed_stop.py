"""Конец показа и тихая пауза прогретого остатка: что гаснет и что остаётся на диске."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from tests.usecases.feed_pack.world import FakeProc, feed, here, lay, packer, tract, vault
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.domain.hls_settings import PACK_DIR
from torrcast.usecases.feed_pack.feed_stop import _rest, _stop
from torrcast.usecases.feed_pack.feed_sweep import _sweep

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Recoder:
    stopped: list[int] = field(default_factory=list)

    def stop(self) -> None:
        self.stopped.append(1)


def test_a_wholly_warmed_rest_puts_the_live_packing_out(tmp_path: Path) -> None:
    """Держать упаковку дальше значит тянуть из раздачи то, что уже лежит на диске."""
    show = feed(tmp_path, vault=vault(tmp_path))
    show.packer = packer(tmp_path, first=0, out=show.out)

    assert _rest(show) is True
    assert show.packer.halted is True and show.packer.stopped == "весь остаток прогрет"


def test_without_the_warmed_film_or_a_run_there_is_nothing_to_put_out(tmp_path: Path) -> None:
    """Гасить нечего: ни прогретого, ни живого прогона - и второй раз тоже нечего."""
    assert _rest(feed(tmp_path)) is False

    show = feed(tmp_path, vault=vault(tmp_path))
    assert _rest(show) is False

    show.packer = packer(tmp_path, first=0, out=show.out, halted=True)
    assert _rest(show) is False


def test_rest_cannot_stop_the_run_replaced_by_the_clock(tmp_path: Path) -> None:
    """Решение о паузе и замена оборванного прогона не пересекаются."""
    tract(now=100.0, spawn=here)
    show = feed(tmp_path, vault=vault(tmp_path))
    fresh = packer(tmp_path, first=3, out=show.out)

    class TurningPacker(Packer):
        turned = False

        def __getattribute__(self, name: str) -> object:
            if name == "halted" and not type(self).turned:
                type(self).turned = True
                _sweep(show, lambda _slot: setattr(show, "packer", fresh))
            return super().__getattribute__(name)

    old = packer(
        tmp_path,
        kind=TurningPacker,
        first=0,
        edge=2,
        out=show.out,
        proc=FakeProc(code=1),
    )
    show.packer = old

    assert _rest(show) is True
    assert show.packer is old and old.halted and not fresh.halted


def test_the_end_of_the_show_closes_the_feed_for_good(tmp_path: Path) -> None:
    """Поток раздачи, спящий в запросе сегмента до двух минут, не должен поднять новый ffmpeg."""
    forgotten: list[Path] = []
    tract(forget_flag=forgotten.append)
    recoder = _Recoder()
    show = feed(tmp_path, recoder=recoder)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.out, 0)
    lay(show.out, 1)
    (show.out / _state.RECODE_DIR).mkdir(parents=True, exist_ok=True)

    _stop(show)

    assert show.trouble() == "показ окончен"
    assert recoder.stopped == [1] and show.packer.stopped == ""
    assert list(show.out.glob("v*.ts")) == []
    assert not (show.out / PACK_DIR).exists()
    assert not (show.out / _state.RECODE_DIR).exists()
    assert forgotten == [show.out], "флажок картинки пережил конец показа"


def test_a_show_that_already_failed_keeps_its_own_reason(tmp_path: Path) -> None:
    """Приговор упаковки не переписывается словами «показ окончен»: причина одна и первая."""
    tract(forget_flag=lambda out: None)
    show = feed(tmp_path)
    show.fatal = "упаковка оборвалась (молча, код 0)"

    _stop(show)

    assert show.trouble() == "упаковка оборвалась (молча, код 0)"
