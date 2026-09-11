#!/usr/bin/env python3
"""Обе границы молчания вкладки: где показ помечает сеанс «lost», где закрывает его штатно.

Инструмент разработчика: в устанавливаемый пакет не входит. Кормит
:class:`torrcast.adapters.browser.browser_receiver.BrowserReceiver` одной позицией и
дальше замолкает - ровно так, как молчит вкладка, у которой встала страница или упала
сеть, - и по секундам стенных часов смотрит, когда :meth:`~torrcast.adapters.browser.
browser_receiver.BrowserReceiver.position` называет сеанс потерянным, а когда -
пометкой ``playing=False``, той же самой, по которой держатель показа
(:func:`torrcast.usecases.revive_playback._hold._hold`) закрывает потерянный телевизор.

    python3 scripts/staleprobe.py --card TC-1108

Прогон реальный, не ускоренный: ждёт настоящие секунды настоящими часами, потому что
порог живёт в профиле как секунды НАСТОЯЩЕГО молчания, а не как число шагов цикла.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probestamp import run_where, stamp

from torrcast.adapters.browser.browser_receiver import BrowserReceiver
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.adapters.system_clock import CLOCK
from torrcast.domain.position import Position


def _wait_for(
    receiver: BrowserReceiver, started: float, done: Callable[[Position], bool], ceiling: float
) -> float:
    """Секунды до первого раза, когда ``done`` сказал правду; таймаут - :class:`SystemExit`."""
    while True:
        position = receiver.position()
        elapsed = time.monotonic() - started
        if done(position):
            return elapsed
        if elapsed > ceiling:
            raise SystemExit(f"не дождался за {ceiling:.1f} с: последнее слово {position}")
        time.sleep(0.5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", help="карточка замера; без неё местом станет дата прогона")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        receiver = BrowserReceiver(out)
        receiver.play("http://x/out.m3u8", title="проба молчания", at=0.0)
        key = read_web_box(out)["key"]
        write_web_position(out, key=key, pos=1.0, dur=600.0, phase="playing", wall=CLOCK.wall())

        ceiling = receiver.gone_after + 15.0
        started = time.monotonic()
        lost_at = _wait_for(receiver, started, lambda p: p.state == "lost", ceiling)
        print(f"lost на {lost_at:.1f} с молчания (порог вкладки {receiver.lost_after:.1f} с)")
        gone_at = _wait_for(receiver, started, lambda p: p.playing is False, ceiling)
        gone_after = receiver.gone_after
        print(f"gone на {gone_at:.1f} с молчания, playing=False (порог {gone_after:.1f} с)")

    print(
        stamp(
            "staleprobe",
            "не при чём",
            run_where(args.card),
            [f"lost {lost_at:.1f} с", f"gone {gone_at:.1f} с"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
