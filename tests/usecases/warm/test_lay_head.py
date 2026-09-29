"""Голова показа ложится на полку склейкой: картинка перекода, звук копии того же места."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.usecases.warm.world import grid, lay, vault, world
from torrcast.domain.segment_container import MPEGTS
from torrcast.usecases.warm.lay_head import WORK, lay_head

if TYPE_CHECKING:
    from pathlib import Path

#: Цель перекода: поддельный ffmpeg её не читает, она только едет в команду.
_ENCODE: Any = object()


@dataclass
class _Packs:
    """Оба ffmpeg захода: каждый сразу отдаёт свой кусок и выходит."""

    started: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)

    def start(self, command: list[str], out: Path, *_args: Any, **_kwargs: Any) -> Any:
        packs = self

        class _Run:
            edge = int(command[0])

            def publish(self) -> None:
                (out / f"v{self.edge}.ts").write_bytes(out.name.encode())

            def poll(self) -> int | None:
                return 0

            def stop(self, keep_files: bool = False, reason: str = "") -> None:
                del keep_files, reason
                packs.stopped.append(out.name)

        self.started.append(out.name)
        return _Run()


class _Mixed(list[tuple[bytes, bytes]]):
    """Что склейка получила: картинку и звук."""


def _world(packs: _Packs, mixed: _Mixed, fits: bool = True) -> None:
    def spot_out(slot: int, laid: Path, copy: Path, cap: int, container: Any) -> bool:
        del slot, cap, container
        mixed.append((laid.read_bytes(), copy.read_bytes()))
        laid.write_bytes(b"mixed")
        return fits

    world(
        packer=packs,
        pack=lambda _source, _audio, _run, _grid, slot, *_a, **_k: [str(slot)],
        pilot=lambda _source, at: (at, at),
        lay_spot=spot_out,
    )


def _lay(store: Any, halt: threading.Event | None = None) -> bool:
    return lay_head(
        store, "http://ts/stream", 1, "", grid(), 0, _ENCODE, 1 << 30, MPEGTS,
        halt or threading.Event(),
    )  # fmt: skip


def test_the_head_lands_on_the_shelf_as_a_mix_and_is_marked_served(tmp_path: Path) -> None:
    """Картинка - перекода, звук - копии; кусок на полке помечен как отданный спот."""
    packs, mixed = _Packs(), _Mixed()
    _world(packs, mixed)
    store = vault(tmp_path)

    assert _lay(store) is True
    assert mixed == [(b"code", b"copy")], "склейка взяла не те куски"
    assert store.path(0).read_bytes() == b"mixed", "на полку лёг не склеенный кусок"
    assert store.spot(0).exists(), "голова на полке без метки спота: показ примет её за копию"
    assert not (store.dir / WORK).exists(), "рабочий каталог головы остался на полке"
    assert sorted(packs.stopped) == ["code", "copy"]


def test_a_head_heavier_than_the_receiver_takes_stays_off_the_shelf(tmp_path: Path) -> None:
    """Склейка не влезла в потолок приёмника: полка остаётся пустой, показ кодирует сам."""
    packs, mixed = _Packs(), _Mixed()
    _world(packs, mixed, fits=False)
    store = vault(tmp_path)

    assert _lay(store) is False
    assert not store.have(0)


def test_a_dropped_head_puts_nothing_on_the_shelf(tmp_path: Path) -> None:
    """Карточка ушла до конца захода: оба ffmpeg снимаются, полка не трогается."""
    packs, mixed = _Packs(), _Mixed()
    _world(packs, mixed)
    store = vault(tmp_path)
    halt = threading.Event()
    halt.set()

    assert _lay(store, halt) is False
    assert not store.have(0)
    assert mixed == [], "снятая голова всё равно склеивалась"
    assert sorted(packs.stopped) == ["code", "copy"], "снятый заход оставил ffmpeg жить"


def test_a_served_head_already_on_the_shelf_starts_no_ffmpeg(tmp_path: Path) -> None:
    """Голова уже лежит отданным спотом: второй заход не тратит на неё процессор."""
    packs, mixed = _Packs(), _Mixed()
    _world(packs, mixed)
    store = vault(tmp_path)
    lay(store, 0)
    store.served.mark(0)

    assert _lay(store) is True
    assert packs.started == []
