"""Голова процесса: одна на ключ полки, карточка снимает только свою, показ - ничью."""

from __future__ import annotations

import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.segment_container import MPEGTS
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.playback import head_ahead
from torrcast.usecases.playback.head_ahead import HeadAhead

_ENTRY: Any = SimpleNamespace(audio=1)
#: Цель сетки и предел приёмника - разные числа, как у вкладки: голова обязана взять предел.
_PROFILE: Any = SimpleNamespace(max_segment_bytes=28_000_000, segment_limit=80_000_000)


def _now(job: Any) -> None:
    job()


def _heads(monkeypatch: pytest.MonkeyPatch, *keys: str) -> None:
    """Каждый следующий ``_plan`` называет следующий ключ полки."""
    queue = list(keys)

    def plan(*_args: object) -> Any:
        return SimpleNamespace(
            vault=SimpleNamespace(key=queue.pop(0)), source="s", voice="", grid=None, slot=0,
            encode=None, splice=True,
        )  # fmt: skip

    monkeypatch.setattr(head_ahead, "_plan", plan)


def _want(ahead: HeadAhead, owner: str = "") -> None:
    ahead.want(Config(), _PROFILE, object(), _ENTRY, owner=owner)  # type: ignore[arg-type]


def test_leaving_the_card_stops_its_own_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карточка ушла, пока голова кодируется: заход снимается, играть её не будут."""
    _heads(monkeypatch, "k")
    halts: list[threading.Event] = []
    ahead = HeadAhead(spawn=_now)

    def lay(*args: Any, **_kw: Any) -> bool:
        halts.append(args[-1])
        ahead.drop("кино")
        return False

    ahead.lay = lay
    _want(ahead, owner="кино")

    assert halts[0].is_set(), "ушедшая карточка оставила голову кодироваться"


def test_another_card_leaving_keeps_the_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """Чужая карточка голову не снимает: страница ушла не с этой картины."""
    _heads(monkeypatch, "k")
    halts: list[threading.Event] = []
    ahead = HeadAhead(spawn=_now)

    def lay(*args: Any, **_kw: Any) -> bool:
        halts.append(args[-1])
        ahead.drop("другое")
        return True

    ahead.lay = lay
    _want(ahead, owner="кино")

    assert not halts[0].is_set()


def test_the_click_takes_the_card_head_over_and_does_not_lay_it_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Клик по той же раздаче вторую голову не заводит, и уход карточки её уже не снимает."""
    _heads(monkeypatch, "k", "k")
    halts: list[threading.Event] = []
    ahead = HeadAhead(spawn=_now)

    def lay(*args: Any, **_kw: Any) -> bool:
        halts.append(args[-1])
        _want(ahead)  # клик пришёл, пока голова карточки кодируется
        ahead.drop("кино")  # страница ушла с карточки на показ
        return True

    ahead.lay = lay
    _want(ahead, owner="кино")

    assert len(halts) == 1, "одну и ту же голову кодировали дважды"
    assert not halts[0].is_set(), "уход карточки снял голову, которую уже ждёт показ"


def test_a_new_head_stops_the_old_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Другая раздача - другая голова: прежняя снимается, ядра нужны новой."""
    _heads(monkeypatch, "old", "new")
    halts: list[threading.Event] = []
    ahead = HeadAhead(spawn=_now)

    def lay(*args: Any, **_kw: Any) -> bool:
        halts.append(args[-1])
        if len(halts) == 1:
            _want(ahead)
        return True

    ahead.lay = lay
    _want(ahead, owner="кино")

    assert len(halts) == 2
    assert halts[0].is_set(), "прежняя голова кодировалась рядом с новой"
    assert not halts[1].is_set()


def test_a_failed_plan_lays_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Раздача не ответила о файлах: заранее голову не кладут, показ возьмёт её сам."""

    def plan(*_args: object) -> Any:
        raise TorrcastError("нет ответа")

    monkeypatch.setattr(head_ahead, "_plan", plan)
    laid: list[object] = []

    def lay(*args: object, **_kw: object) -> bool:
        laid.append(args)
        return True

    ahead = HeadAhead(spawn=_now, lay=lay)

    _want(ahead, owner="кино")

    assert laid == []


@pytest.mark.parametrize("late", [True, False], ids=["late", "ahead"])
def test_a_head_planned_after_the_show_is_up_is_not_laid(
    monkeypatch: pytest.MonkeyPatch, late: bool
) -> None:
    """Холодный план кончился после клика: показ кодирует голову сам, вторая - сосед по ядрам."""
    _heads(monkeypatch, "k")
    laid: list[object] = []

    def lay(*args: object, **_kw: object) -> bool:
        laid.append(args)
        return True

    ahead = HeadAhead(spawn=_now, lay=lay)
    ahead.want(Config(), _PROFILE, object(), _ENTRY, owner="кино", late=lambda: late)  # type: ignore[arg-type]

    assert len(laid) == (0 if late else 1)


def test_the_head_is_cut_to_the_receivers_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Голова карточки режется тем же пределом, что показ, а не целью сетки."""
    _heads(monkeypatch, "k")
    caps: list[object] = []
    ahead = HeadAhead(spawn=_now, lay=lambda *args, **_kw: bool(caps.append(args[7])))

    _want(ahead)

    assert caps == [80_000_000]


@pytest.mark.parametrize(
    "config",
    [replace(Config(), warm=False), replace(Config(), recode=False)],
    ids=["warm", "recode"],
)
def test_no_head_without_the_shelf_or_the_recode(config: Config) -> None:
    """Без полки или без перекода класть нечего, и раздачу даже не спрашивают."""
    assert head_ahead._plan(config, CAUTIOUS, object(), _ENTRY) is None  # type: ignore[arg-type]


def test_with_the_shelf_and_the_recode_the_plan_asks_the_torrent() -> None:
    """Положительный контроль к пробе выше: с умолчаниями план идёт к раздаче за файлом."""
    entry: Any = SimpleNamespace(magnet="magnet:?xt=urn:btih:" + "a" * 40, file_idx=1)

    with pytest.raises(AttributeError, match="stream_url"):
        head_ahead._plan(Config(), CAUTIOUS, object(), entry)  # type: ignore[arg-type]


def test_a_whole_recode_file_lays_its_head_under_the_whole_shelf_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Файл идёт перекодом целиком: голова - его же перекод, без склейки, на полке показа."""
    whole: Any = SimpleNamespace(name="целиком")
    grid: Any = SimpleNamespace(slot_at=lambda _pos: 0)
    monkeypatch.setattr(head_ahead, "entry_layout", lambda *_a, **_k: (grid, whole))
    monkeypatch.setattr(head_ahead, "voice_source", lambda *_a: "")
    keys: list[tuple[Any, ...]] = []

    def key(*args: Any) -> str:
        keys.append(args)
        return "ключ"

    monkeypatch.setattr(head_ahead, "warm_key", key)
    engine: Any = SimpleNamespace(stream_url=lambda *_a: "src", files=lambda _t: [])
    entry: Any = SimpleNamespace(
        magnet="magnet:?xt=urn:btih:" + "a" * 40, file_idx=1, audio=2, vbps=1.0, dur=60.0,
        codec="mpeg4", depth=8, frame=None, hdr="", vbps_estimated=False, pos=0.0,
        title="кино", label="",
    )  # fmt: skip
    config = replace(Config(), warm_dir=str(tmp_path))

    head = head_ahead._plan(config, CAUTIOUS, engine, entry)

    assert head is not None, "сплошной перекод остался без головы заранее"
    assert head.splice is False and head.encode is whole
    assert keys == [("src", 2, grid, whole, (), MPEGTS, "", whole)]
    assert head.vault.key == "ключ"
