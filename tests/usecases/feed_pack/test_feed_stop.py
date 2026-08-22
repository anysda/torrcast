"""Конец показа и тихая пауза прогретого остатка: что гаснет и что остаётся на диске."""

from __future__ import annotations

import ast
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import torrcast.usecases.feed_pack as feed_pack
import torrcast.usecases.feed_pack._state as _state
from tests.usecases.feed_pack.world import (
    FakeProc,
    feed,
    here,
    lay,
    packer,
    signals,
    tract,
    vault,
)
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.domain.hls_settings import PACK_DIR
from torrcast.usecases.feed_pack.feed_stop import _rest, _stop
from torrcast.usecases.feed_pack.feed_sweep import _sweep


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


def _waits_for_the_lock(node: ast.AST) -> bool:
    """Берут ли тут замок ленты с ожиданием: ``with state.lock`` или ``acquire`` без отказа."""
    if isinstance(node, ast.With):
        return any(
            isinstance(item.context_expr, ast.Attribute) and item.context_expr.attr == "lock"
            for item in node.items
        )
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    owner = node.func.value
    if node.func.attr != "acquire" or not isinstance(owner, ast.Attribute) or owner.attr != "lock":
        return False
    refused = [
        word
        for word in node.keywords
        if word.arg == "blocking" and isinstance(word.value, ast.Constant)
    ]
    return not any(word.value.value is False for word in refused)  # type: ignore[attr-defined]


def _blocking_grabs() -> list[str]:
    """Единицы ленты, которые ЖДУТ замок, а не отступают перед занятым."""
    where = Path(str(feed_pack.__file__)).parent
    found: set[str] = set()
    for path in sorted(where.glob("*.py")):
        for unit in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(unit, ast.FunctionDef):
                continue
            if any(_waits_for_the_lock(inner) for inner in ast.walk(unit)):
                found.add(f"{path.stem}.{unit.name}")
    return sorted(found)


def test_the_lock_is_waited_for_at_the_end_of_the_show_and_nowhere_else() -> None:
    """Ждать замок ленты можно ровно на сносе показа - и больше нигде.

    Замок держит подъём оборванного прогона до минуты по потолку пробного. Ожидание,
    попавшее на круг опроса приёмника (те же две секунды), ослепило бы разом ВСЕ метрики
    показа - место, подвис, перемотку, - а не только ту упаковку, которую поднимают.
    """
    assert _blocking_grabs() == ["feed_stop._stop"], "ожидание замка вернулось на часы показа"


@pytest.mark.machine
def test_the_end_of_the_show_waits_for_the_lift_it_found_in_flight(tmp_path: Path) -> None:
    """Снос показа не встревает в идущий подъём: он ждёт его и гасит доставленный прогон.

    🔴 Замок тут единственный на всю ленту, и он закрывает замену прогона
    (:attr:`_State.packer`). Отсутствие замка видно ТОЛЬКО при конкуренции, поэтому
    конкурент настоящий: без замка снос гасит прогон, который подъём уже сменил, а
    свежий ffmpeg остаётся читать раздачу в каталог, которого больше нет.

    Замок держат прямо тут, а не поднимают вторым потоком подъём: ждать в пробе минуту
    пробного прогона незачем, а держит его подъём ровно так же.
    """
    tract(forget_flag=lambda out: None)
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=1))
    fresh = packer(tmp_path, first=3, out=show.out, run=tmp_path / "pack-fresh")

    show.lock.acquire()  # подъём в полёте: замок его, пока не кончится пробный прогон
    ending = threading.Thread(target=_stop, args=(show,))
    ending.start()
    try:
        ending.join(0.3)
        assert ending.is_alive(), "снос показа встрял в идущий подъём и погасил чужой прогон"
        show.packer = fresh  # подъём доставил свой прогон и отпускает замок
    finally:
        show.lock.release()
        ending.join(10.0)

    assert not ending.is_alive(), "снос показа не дождался подъёма"
    assert signals(fresh) == ["terminate"], "снос показа не погасил прогон, доставленный подъёмом"
