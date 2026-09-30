#!/usr/bin/env python3
"""Что вкладка Chromium реально играет: кодеки MSE и живой показ до первого кадра.

Инструмент разработчика: в устанавливаемый пакет не входит. Гоняется на машине с
Playwright (``PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers``), как :mod:`decodebench`.
Отвечает на два вопроса профиля вкладки (:data:`torrcast.domain.browser_profile.BROWSER`):

    /path/to/python3 scripts/tabprobe.py codecs --card TC-1259
    /path/to/python3 scripts/tabprobe.py play --base http://host:8098 --query Up \\
        --picture movie:up:2009 --card TC-1259

``codecs`` спрашивает ``MediaSource.isTypeSupported`` по строкам типа, которые
выдаёт наша упаковка и чужие релизы. ``play`` открывает ``/play``, зовёт показ во
вкладке и ждёт, когда ``currentTime`` сдвинется. Кадр судится в самой странице:
центр картинки через canvas, доля светлых точек и разброс яркости - чёрный экран
со сдвигом часов (копия HEVC) так не проходит. Самый тяжёлый кусок берётся из
Resource Timing: это вес, который hls.js реально принял.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from probestamp import run_where, stamp

#: Строки типа: наш кусок MPEG-TS, H.264 по профилям, HEVC, VP9, AV1, mpeg4 и звук.
TYPES = (
    'video/mp2t; codecs="avc1.640028,mp4a.40.2"',
    'video/mp4; codecs="avc1.640028"',
    'video/mp4; codecs="avc1.640033"',
    'video/mp4; codecs="avc1.6E0028"',
    'video/mp4; codecs="hvc1.1.6.L120.90"',
    'video/mp4; codecs="hev1.2.4.L153.90"',
    'video/mp4; codecs="vp09.00.40.08"',
    'video/mp4; codecs="av01.0.08M.08"',
    'video/mp4; codecs="mp4v.20.9"',
    'audio/mp4; codecs="mp4a.40.2"',
    'audio/mp4; codecs="ac-3"',
    'audio/mp4; codecs="ec-3"',
)

#: Кадр в странице: центр видео на canvas, яркость по BT.601.
_LUMA = """() => {
  const v = [...document.querySelectorAll('video')]
    .sort((a, b) => b.currentTime - a.currentTime)[0];
  if (!v || !v.videoWidth) return null;
  const c = document.createElement('canvas'); c.width = 160; c.height = 90;
  const g = c.getContext('2d');
  const w = v.videoWidth, h = v.videoHeight;
  g.drawImage(v, w / 4, h / 4, w / 2, h / 2, 0, 0, 160, 90);
  const d = g.getImageData(0, 0, 160, 90).data; const n = d.length / 4;
  let s = 0, q = 0, lit = 0;
  for (let i = 0; i < d.length; i += 4) {
    const y = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    s += y; q += y * y; if (y >= 25) lit += 1;
  }
  const m = s / n;
  return {t: v.currentTime, mean: m, sd: Math.sqrt(Math.max(0, q / n - m * m)), lit: lit / n};
}"""

_SEGMENTS = """() => performance.getEntriesByType('resource')
  .filter((e) => /\\.(ts|m4s)(\\?|$)/.test(e.name))
  .map((e) => [e.name.split('/').pop(), e.encodedBodySize || e.transferSize || 0])"""


def codecs(page: Any) -> dict[str, bool]:
    """Ответ ``MediaSource.isTypeSupported`` по каждой строке :data:`TYPES`."""
    page.goto("about:blank")
    return dict(
        zip(
            TYPES,
            page.evaluate("(ts) => ts.map((t) => MediaSource.isTypeSupported(t))", list(TYPES)),
            strict=True,
        )
    )


def play(page: Any, args: argparse.Namespace) -> dict[str, Any]:
    """Показ во вкладке: сдвиг часов, кадр не чёрный, самый тяжёлый принятый кусок."""
    page.goto(args.base + "/play", wait_until="load")
    page.wait_for_function("() => window.TCApi")
    body = {"query": args.query, "picture": args.picture, "from_start": True, "here": True}
    page.evaluate("(b) => { window.__t0 = performance.now(); TCApi.play(b); }", body)
    moved = None
    for _ in range(int(args.limit * 4)):
        page.wait_for_timeout(250)
        now = page.evaluate(
            "() => Math.max(0, ...[...document.querySelectorAll('video')]"
            ".map((v) => v.currentTime))"
        )
        if now > 0.05:
            moved = round(page.evaluate("() => (performance.now() - window.__t0) / 1000"), 2)
            break
    frames = []
    if moved is not None:
        for _ in range(3):
            page.wait_for_timeout(int(args.watch * 1000 / 3))
            frames.append(page.evaluate(_LUMA))
    picture = any(f and f["lit"] >= 0.02 and f["sd"] >= 4 for f in frames)
    sizes = page.evaluate(_SEGMENTS)
    heaviest = max(sizes, key=lambda s: s[1]) if sizes else None
    return {
        "moved_s": moved,
        "picture": picture,
        "frames": frames,
        "segments": len(sizes),
        "heaviest": heaviest,
    }


def main(argv: list[str] | None = None) -> int:
    """Прогнать щуп и напечатать ответ JSON и подпись прибора последней строкой."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("codecs", "play"))
    parser.add_argument("--base", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--picture", default="")
    parser.add_argument("--limit", type=float, default=90.0, help="ждать сдвиг часов, с")
    parser.add_argument("--watch", type=float, default=15.0, help="смотреть после сдвига, с")
    parser.add_argument("--card", default=None)
    args = parser.parse_args(argv)
    if args.mode == "play" and not (args.base and args.query):
        parser.error("play: нужны --base и --query")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        found: Any = codecs(page) if args.mode == "codecs" else play(page, args)
        version = browser.version
        browser.close()
    print(json.dumps({"chromium": version, args.mode: found}, ensure_ascii=False, indent=1))
    extra = [f"Chromium {version}"]
    if args.mode == "play":
        extra.append(f"сдвиг {found['moved_s']} с, кадр {'да' if found['picture'] else 'НЕТ'}")
    print(stamp("tabprobe", "mpegts", run_where(args.card), extra))
    ok = args.mode == "codecs" or (found["moved_s"] is not None and found["picture"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
