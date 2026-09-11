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
import time
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
            str(args.span),
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


def _span_of(folder: Path, init: Path, name: str) -> float:
    """Длительность одного куска: сумма длительностей его же кадров.

    🔴 ``format=duration`` тут врёт, и молча: у fMP4-куска своё место на ленте задано
    ``tfdt``, и ffprobe отвечает КОНЦОМ куска на ленте показа, а не его длиной. Взятое
    как длина, оно даёт полку в 2193 с из двенадцати кусков по три минуты.
    """
    joined = folder / "_span.mp4"
    joined.write_bytes(init.read_bytes() + (folder / name).read_bytes())
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=duration_time",
            "-of",
            "csv=p=0",
            str(joined),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    joined.unlink()
    return sum(float(row) for row in out.stdout.split() if row and row != "N/A")


def _shelf(args: argparse.Namespace) -> int:
    """Полка VOD из НАСТОЯЩИХ кусков продукта: вес куска тут не задан, а замерен.

    Ступени `pack` весят ровно столько, сколько заказано - на них не увидеть, что делает
    с вкладкой кусок, который сложился сам. Продукт кладёт свои куски в тёплый склад
    (``/var/lib/torrcast/warm/<ключ>``) рядом с ``init.mp4``, и там они разного веса:
    ровно тот материал, на котором и стоит вопрос про потолок веса.
    """
    folder = Path(args.dir)
    init = folder / "init.mp4"
    names = sorted(
        (f.name for f in folder.glob("v*.m4s")),
        key=lambda n: int(n[1:].split(".")[0]),
    )
    if args.first is not None:
        names = [n for n in names if int(n[1:].split(".")[0]) >= args.first]
    names = names[: args.count]
    if not init.exists() or not names:
        print(f"в {folder} нет init.mp4 или кусков v*.m4s", file=sys.stderr)
        return 1
    (folder / "decode_probe.html").write_text(_HARNESS, encoding="utf-8")
    spans = [_span_of(folder, init, name) for name in names]
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        f"#EXT-X-TARGETDURATION:{int(max(spans)) + 1}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        '#EXT-X-MAP:URI="init.mp4"',
    ]
    for name, span in zip(names, spans, strict=True):
        lines += [f"#EXTINF:{span:.3f},", name]
    lines.append("#EXT-X-ENDLIST")
    (folder / args.name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    weights = [(folder / n).stat().st_size for n in names]
    total = sum(spans)
    print(f"полка {folder / args.name}: кусков {len(names)}, плёнки {total:.1f} с")
    print(f"вес МБ: {[round(w / 1e6, 1) for w in weights]}")
    print(f"самый тяжёлый {max(weights) / 1e6:.1f} МБ, самый лёгкий {min(weights) / 1e6:.1f} МБ")
    print("положи hls.min.js рядом - гарнитура сама его не тянет")
    return 0


def _weigh(args: argparse.Namespace) -> int:
    """Прогнать одну готовую полку и сказать, держит ли вкладка РЕАЛЬНЫЙ темп.

    Мера тут не «доиграл ли», а «за сколько настенных секунд прошло столько-то плёнки»:
    декодер, который не тянет, отстаёт по темпу, не роняя ни кадра (это уже ловилось на
    ступени 60 Мбит/с: headless Chromium на CT502 за 60 с настенных дошёл до 39.7 с из
    40.87, а 10-50 Мбит/с доиграли в реальном темпе).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright не поставлен в этом интерпретаторе", file=sys.stderr)
        return 1
    url = f"{args.base}/{args.name}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(f"{args.base}/decode_probe.html")
        began = time.monotonic()
        result = cast(
            "dict[str, Any]",
            page.evaluate("([u, t]) => window.runProbe(u, t)", [url, args.timeout * 1000]),
        )
        spent = time.monotonic() - began
        browser.close()
    reached = float(result.get("pos") or result.get("duration") or 0.0)
    print(f"полка {url}: {json.dumps(result)}")
    pace = f"темп {reached / spent:.2f}x" if spent else "темп не считан"
    print(f"плёнки пройдено {reached:.1f} с за {spent:.1f} с настенных - {pace}")
    print(
        stamp(
            "decodebench",
            "fmp4",
            run_where(args.card),
            [f"{reached:.1f}s/{spent:.1f}s", f"dropped={result.get('dropped')}"],
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
    # Вес куска и его битрейт - РАЗНЫЕ вопросы, а перепутать их легко: тяжелее кусок
    # выходит и от того, и от другого. Длина разводит их: при своём битрейте ступень
    # тяжелеет только временем, и декодер тут ни при чём.
    pack.add_argument("--span", type=float, default=4.0, help="длина куска, секунды")
    pack.set_defaults(func=_pack)

    probe = sub.add_parser("probe", help="прогнать ступени в браузере и снять счётчик")
    probe.add_argument("--base", required=True, help="http-корень с уложенными ступенями")
    probe.add_argument("--tiers", required=True, help="список Мбит/с через запятую")
    probe.add_argument("--timeout", type=float, default=60.0)
    probe.add_argument("--card", help="карточка замера; без неё местом станет дата прогона")
    probe.set_defaults(func=_probe)

    shelf = sub.add_parser("shelf", help="собрать полку VOD из настоящих кусков продукта")
    shelf.add_argument("--dir", required=True, help="каталог с init.mp4 и v*.m4s")
    shelf.add_argument("--name", default="shelf.m3u8", help="имя плейлиста в том же каталоге")
    shelf.add_argument("--first", type=int, help="с какого слота начать (по умолчанию с первого)")
    shelf.add_argument("--count", type=int, default=12, help="сколько кусков взять")
    shelf.set_defaults(func=_shelf)

    weigh = sub.add_parser("weigh", help="прогнать полку и снять темп показа")
    weigh.add_argument("--base", required=True, help="http-корень с полкой")
    weigh.add_argument("--name", default="shelf.m3u8", help="имя плейлиста")
    weigh.add_argument("--timeout", type=float, default=180.0)
    weigh.add_argument("--card", help="карточка замера; без неё местом станет дата прогона")
    weigh.set_defaults(func=_weigh)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
