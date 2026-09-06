#!/usr/bin/env python3
"""Потолок разбора у вкладки-приёмника: где именно декодер начинает отставать.

Инструмент разработчика: в устанавливаемый пакет не входит. Гоняется НА СТЕНДЕ рядом
с реальным браузером (у CT502 - ``PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`` и
``chromium_headless_shell``), потому что мерит живой разбор кадра, а не серверный
перекод (тот меряет :mod:`recodebench` - вопрос другой стороны провода).

Метрика - ``HTMLVideoElement.getVideoPlaybackQuality()``: пропущенные кадры и то,
успела ли позиция дойти до конца ролика за разумное время (декодер, который просто
отстаёт, роняет кадры не всегда - он может держать нулевой счётчик и застревать
по темпу, поэтому подкоманда ``probe`` смотрит на оба признака сразу).

Два шага, порознь:

    python3 scripts/decodebench.py pack --src in.ts --out /srv/tiers --tiers 10,20,30,40,50,60
    /opt/pwenv/bin/python3 scripts/decodebench.py probe --base http://host:8098 \\
        --tiers 10,20,30,40,50,60 --card TC-1108

``pack`` нарезает fMP4-HLS по ступеням Мбит/с из уже готового исходника (нужен только
``ffmpeg`` в PATH - как ``adb``/``cast`` у соседних щупов, без новой зависимости в
pyproject). ``probe`` водит браузер через Playwright - ставится на стенде отдельно
(``pip install playwright && playwright install chromium``), в основной пакет проекта
не входит по той же причине, по которой ``framebench`` не тянет adb в pyproject.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from probestamp import run_where, stamp

#: Разбор мимо hls.js кладут рядом руками - см. предупреждение в probe().
_HARNESS = """<!doctype html>
<html><body>
<video id="v" muted style="width:640px"></video>
<script src="hls.min.js"></script>
<script>
window.runProbe = function (url, timeoutMs) {
  return new Promise(function (resolve) {
    var video = document.getElementById("v");
    var done = false;
    function finish(extra) {
      if (done) return;
      done = true;
      var q = video.getVideoPlaybackQuality();
      resolve(Object.assign({
        dropped: q.droppedVideoFrames,
        total: q.totalVideoFrames,
        duration: video.duration,
      }, extra || {}));
    }
    video.addEventListener("ended", function () { finish(); });
    setTimeout(function () {
      finish({timedOut: true, pos: video.currentTime});
    }, timeoutMs || 60000);
    if (window.Hls && Hls.isSupported()) {
      var hls = new Hls();
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, function () { video.play(); });
    } else {
      video.src = url;
      video.addEventListener("loadedmetadata", function () { video.play(); });
    }
  });
};
</script>
</body></html>
"""


def _pack(args: argparse.Namespace) -> int:
    """Нарезать один и тот же исходник на несколько ступеней битрейта."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decode_probe.html").write_text(_HARNESS, encoding="utf-8")
    for mbit in [int(t) for t in args.tiers.split(",")]:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            args.src,
            "-vf",
            f"scale={args.width}:{args.height}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            f"{mbit}M",
            "-maxrate",
            f"{mbit}M",
            "-bufsize",
            f"{mbit}M",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-g",
            "60",
            "-f",
            "hls",
            "-hls_time",
            "4",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_type",
            "fmp4",
            "-hls_fmp4_init_filename",
            f"init_{mbit}.mp4",
            "-hls_segment_filename",
            str(out / f"v{mbit}_%03d.m4s"),
            str(out / f"out_{mbit}.m3u8"),
        ]
        subprocess.run(cmd, check=True)
        print(f"уложена ступень {mbit} Мбит/с -> {out / f'out_{mbit}.m3u8'}")
    print(f"положи hls.min.js рядом ({out / 'hls.min.js'}) - гарнитура сама его не тянет")
    return 0


def _probe_one(page: Any, base: str, mbit: int, timeout: float) -> dict[str, Any]:
    url = f"{base}/decode_probe.html"
    page.goto(url)
    src = f"{base}/out_{mbit}.m3u8"
    result = page.evaluate("([u, t]) => window.runProbe(u, t)", [src, timeout * 1000])
    return cast(dict[str, Any], result)


def _probe(args: argparse.Namespace) -> int:
    """Прогнать ступени по очереди и напечатать честную подпись прибора."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright не поставлен в этом интерпретаторе - "
            "pip install playwright && playwright install chromium\n"
            "гоняй той же командой, что и на CT502: /opt/pwenv/bin/python3 ...",
            file=sys.stderr,
        )
        return 1

    tiers = [int(t) for t in args.tiers.split(",")]
    results: dict[str, dict[str, Any]] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for mbit in tiers:
            r = _probe_one(page, args.base, mbit, args.timeout)
            results[str(mbit)] = r
            print(f"ступень {mbit} Мбит/с -> {json.dumps(r)}")
        browser.close()

    # 🔴 Подпись прибора печатается вместе с числами этого прогона - вопрос «чем
    # снято» не должен отвечаться историей git (:mod:`probestamp`, TC-870).
    print(
        stamp(
            "decodebench",
            "fmp4",
            run_where(args.card),
            [f"{m}:{results[m]['dropped']}/{results[m]['total']}" for m in results],
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    pack = sub.add_parser("pack", help="нарезать ступени битрейта из исходника")
    pack.add_argument("--src", required=True, help="путь к исходному видео")
    pack.add_argument("--out", required=True, help="каталог для ступеней")
    pack.add_argument("--tiers", required=True, help="список Мбит/с через запятую")
    pack.add_argument("--width", type=int, default=1920)
    pack.add_argument("--height", type=int, default=1080)
    pack.set_defaults(func=_pack)

    probe = sub.add_parser("probe", help="прогнать ступени в браузере и снять счётчик")
    probe.add_argument("--base", required=True, help="http-корень с уложенными ступенями")
    probe.add_argument("--tiers", required=True, help="список Мбит/с через запятую")
    probe.add_argument("--timeout", type=float, default=60.0)
    probe.add_argument("--card", help="карточка замера; без неё местом станет дата прогона")
    probe.set_defaults(func=_probe)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
