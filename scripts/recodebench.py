#!/usr/bin/env python3
"""Замеры под динамический битрейт: скорость кодека и профиль тяжести фильма.

Четыре режима, и все они отвечают на вопросы, от которых зависит сама возможность затеи:

``--speed ФАЙЛ``
    Сколько реального времени стоит секунда 1080p на этой машине — по каждому пресету
    libx264. Вход берётся готовым куском фильма (см. ``--dump``), чтобы рой и сеть в
    замер не лезли. Пример замера на 4 vCPU (Xeon E5-2696 v4, вход 23.7 Мбит/с, кап 12/13):
    ultrafast 4.36×, superfast 2.62×, veryfast 1.54×, faster 1.04×, fast 0.72×, medium 0.55×.

``--price`` (``--file ФАЙЛ`` или ``--film ХЕШ``)
    Цена **боевого** тракта: ровно та пара «сетка и решение о сплошном перекоде», которую
    собирает показ (:func:`torrcast.cli._layout`), и ровно та команда, которой он пакует
    (:func:`torrcast.stream.ffmpeg_pack_command`). Отличие от ``--speed`` не косметическое:
    там меряется чистая скорость кодека на готовом куске, а тут — секунда показа со всеми
    её слагаемыми, включая подъём ffmpeg, чтение источника, ``-force_key_frames`` по
    границам сетки, ужатие кадра и тонемап. 🔴 Ради этого режима щуп и написан: цену
    сплошного перекода до сих пор мерили одноразовыми скриптами, и каждый мерил своё.

``--profile --film ХЕШ``
    Профиль тяжести фильма по карте опорных кадров: сколько сегментов сетки приёмник не
    потянет, где они стоят и какими сериями идут. Ни одного упакованного сегмента для
    этого не нужно — всё считается из карты.

``--plan ХЕШ --at СКОРОСТЬ``
    Модель показа: успевает ли кодировщик, работая с нулевой секунды и по порядку фильма.
    Отвечает на единственный вопрос, который решает архитектуру, — сколько тяжёлых кусков
    доедет до показа неготовыми.

⚠️ Замер скорости не переносится на машину с другим числом ядер: числа в
:data:`torrcast.recode.PRESETS` сняты на одной машине и на такой же должны пересниматься.

Источник у режимов, которым нужен файл, задаётся двояко: ``--film ХЕШ`` поднимает раздачу
в TorrServer, ``--file ПУТЬ`` берёт файл с диска. Второе — не удобство: карта опорных
кадров снимается Range-запросами (:func:`torrcast.stream.film_keys`), и локальному файлу
поэтому поднимается своя мини-раздача (:func:`seekcheck.serve_file`). Без неё замер на
собственном материале был невозможен вовсе, и цену перекода мерили на чём придётся.
"""

from __future__ import annotations

import argparse
import json
import resource
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from probeprofile import choose as choose_profile
from seekcheck import serve_file

from torrcast.cli import _layout
from torrcast.profile import Profile
from torrcast.recode import Encode, Weights
from torrcast.search import magnet_for
from torrcast.state import Config, load_config
from torrcast.stream import (
    Grid,
    Packer,
    TorrServer,
    ffmpeg_pack_command,
    film_keys,
    grid_for,
    hls_dir,
    pick_video_file,
    probe,
    segment_slot,
)

PRESET_LADDER = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium")


def _film(torrent_hash: str) -> tuple[str, int]:
    """Поднять раздачу и вернуть URL файла видео и его размер."""
    config = load_config()
    torrserver = TorrServer(config.torrserver_url)
    key = torrserver.add(magnet_for(torrent_hash))
    found = pick_video_file(torrserver.wait_files(key, timeout=180.0))
    return torrserver.stream_url(key, found.index), found.size


def _source(torrent_hash: str | None, local: Path | None) -> tuple[str, int]:
    """URL источника и его размер: раздача из TorrServer или файл с диска.

    Локальному файлу поднимается мини-раздача с Range: карту опорных кадров иначе не
    снять, а без карты нет ни сетки, ни профиля тяжести (:func:`seekcheck.serve_file`).
    """
    if local is not None:
        path = local.resolve()
        return serve_file(path), path.stat().st_size
    assert torrent_hash is not None  # argparse требует один из двух источников
    return _film(torrent_hash)


def _grid_of(url: str, step: float) -> tuple[Grid, object]:
    keys = film_keys(url)
    grid = grid_for(url, keys.duration, step, True, say=lambda t: print(f"  {t}"))
    return grid, keys


def speed(path: Path) -> None:
    """Таблица «пресет → во сколько раз быстрее реального времени»."""
    duration = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip().split(",")[0]
    )  # fmt: skip
    size = path.stat().st_size
    print(f"вход: {duration:.2f} с, {size / 2**20:.1f} МБ, {size * 8 / duration / 1e6:.2f} Мбит/с")
    print(f"\n{'пресет':<11}{'wall, с':>9}{'xRT':>8}{'Мбит/с':>10}")
    out = path.with_name("bench-out.ts")
    for preset in PRESET_LADDER:
        encode = Encode(preset=preset, mbit=12.0)
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
            "-map", "0:v:0", "-map", "0:a:0",
            # Принудительные опорные кадры тут ни при чём: меряем чистую скорость кодека.
            *[a for a in encode.args(Grid((0.0,), duration), 0, 0)
              if a != "-force_key_frames"][:-1],
            "-g", "250", "-c:a", "copy", "-f", "mpegts", str(out),
        ]  # fmt: skip
        began = time.monotonic()
        subprocess.run(command, capture_output=True, check=True)
        spent = time.monotonic() - began
        got = out.stat().st_size
        print(
            f"{preset:<11}{spent:>9.1f}{duration / spent:>7.2f}x{got * 8 / duration / 1e6:>10.2f}"
        )
        out.unlink(missing_ok=True)


def _cpu_seconds() -> float:
    """Процессорное время всех дочерних процессов, секунды.

    Считается им, а не стенными часами, и это не педантизм: замер идёт на машине с
    соседями, и стенка на ней мерит очередь к процессору, а не цену перекода.
    """
    spent = resource.getrusage(resource.RUSAGE_CHILDREN)
    return spent.ru_utime + spent.ru_stime


def price(
    source: str, slot: int, count: int, where: Path, mbit: float, config: Config, profile: Profile
) -> None:
    """Цена боевого тракта: та же пара «сетка + сплошной перекод», которой пакует показ.

    Собирается она ровно одним вызовом :func:`torrcast.cli._layout` — не повторяется здесь
    и не подгоняется. Всё, что щуп добавляет от себя, — часы и весы:

    * сколько процессорных секунд стоит секунда фильма (``xCPU``) и сколько стенных (``xRT``);
    * сколько весит каждый упакованный кусок против того, что сетке **обещали**
      (``fixed_mbit`` = потолок кодера, не цель);
    * не родился ли кусок за потолком приёмника ещё до всякой выкладки.

    ⚠️ Хвост сетки в судьи не берётся: он склеивается с последним куском и на потолок веса
    не проверялся никогда (:meth:`torrcast.stream.Grid.on_keyframes`).
    """
    from torrcast.stream import AUDIO_MBIT, TS_OVERHEAD

    if mbit > 0:
        config = replace(config, recode_mbit=mbit)
    media = probe(source)
    video_mbit = max(0.0, media.video_bps / 1e6)
    print(
        f"источник: {source}\n"
        f"  {media.duration:.1f} с, {media.video} {media.frame}p, глубина {media.depth}, "
        f"HDR {media.hdr}, видео {video_mbit:.2f} Мбит/с"
    )
    grid, whole = _layout(
        config,
        source,
        media.duration,
        media.video or "",
        video_mbit,
        say=lambda t: print(f"  {t}"),
        depth=media.depth,
        profile=profile,
        frame=media.frame,
        hdr=media.hdr,
    )
    if whole is None:
        print("сплошного перекода нет: файл уезжает копией - мерить тут нечего")
        return
    promise = (whole.maxrate + AUDIO_MBIT) * TS_OVERHEAD
    print(
        f"сплошной перекод: {whole.preset}, цель {whole.mbit:.2f} Мбит/с, "
        f"потолок кодера {whole.maxrate:.2f}, кадр {whole.out_frame}p, тонемап {whole.hdr}\n"
        f"сетке обещано {promise:.2f} Мбит/с доставленных; "
        f"потолок приёмника {profile.max_segment_bytes / 2**20:.1f} МБ"
    )

    until = min(slot + count - 1, grid.count - 1)
    out = hls_dir(str(where))
    run = where / "run"
    # ⚠️ Пробного захода тут нет и быть не может: у перекодирующего прогона докатки нет,
    # ``-ss`` точен (:func:`torrcast.stream.ffmpeg_pack_command`).
    command = ffmpeg_pack_command(
        source,
        0,
        str(run),
        cast(Grid, grid),
        slot,
        grid.start(slot),
        readrate=0.0,
        encode=whole,
        until=until,
    )
    print(f"\nпакуем v{slot}..v{until} тем же ffmpeg, что и показ:\n  {' '.join(command)}\n")
    was_cpu = _cpu_seconds()
    began = time.monotonic()
    packer = Packer.start(command, out, run, slot, last=until, grid=grid)
    # Ждём, пока ffmpeg выйдет САМ: заход ограничен ``-to``, и код возврата тут - его
    # собственный. Сними мы прогон по достижении края (``edge``), в отчёте стоял бы наш
    # же SIGTERM, то есть замер расписывался бы в успехе, которого не проверял.
    while packer.poll() is None and time.monotonic() - began < 1800:
        packer.publish()
        time.sleep(0.5)
    code = packer.poll()
    packer.publish()  # код 0 - дописан и последний кусок, до этой строки он не выложен
    packer.stop(keep_files=True, reason="замер окончен")
    if code:
        print(f"⚠️ прогон кончился не сам: {packer.why()}")
    wall = time.monotonic() - began
    cpu = _cpu_seconds() - was_cpu

    made = sorted((s, p) for p in out.glob("v*.ts") if slot <= (s := segment_slot(p.name)) <= until)
    seconds = sum(grid.span(s) for s, _ in made)
    print(f"{'кусок':<8}{'с':>7}{'МБ':>8}{'обещано МБ':>12}{'Мбит/с':>9}{'промах':>9}")
    worst = 0.0
    for number, path in made:
        span = grid.span(number)
        got = path.stat().st_size
        due = promise * span * 1e6 / 8
        tail = number >= grid.count - 1
        miss = got / due - 1 if due > 0 else 0.0
        if not tail:
            worst = max(worst, got / profile.max_segment_bytes)
        print(
            f"v{number:<7}{span:>7.2f}{got / 2**20:>8.2f}{due / 2**20:>12.2f}"
            f"{got * 8 / span / 1e6:>9.2f}{miss * 100:>8.1f}%{' хвост' if tail else ''}"
        )
    print(
        f"\nупаковано {len(made)} кусков, {seconds:.1f} с фильма; код возврата ffmpeg {code}\n"
        f"стенка {wall:.1f} с ({seconds / wall if wall > 0 else 0:.2f}xRT), "
        f"процессор {cpu:.1f} с ({seconds / cpu if cpu > 0 else 0:.2f}xCPU, "
        f"{cpu / seconds if seconds > 0 else 0:.2f} с CPU на секунду показа)\n"
        f"самый тяжёлый кусок (без хвоста): {100 * worst:.1f}% потолка приёмника"
    )


def calibrate(
    url: str, slot: int, count: int, where: Path, step: float, config: Config, profile: Profile
) -> None:
    """Чем врёт ранняя прикидка тяжести: предсказание против выложенной копии, кусок за куском.

    Профиль тяжести (:class:`torrcast.recode.Weights`) считается по карте опорных кадров до
    первого сегмента, и на нём стоит решение «класть копией или перекодировать». Байты
    карты — контейнер целиком, поэтому из них вычитается поправка «контейнер → ТВ»
    (:attr:`~torrcast.recode.Weights.extra`), а она до первой калибровки известна только
    паспортом ffprobe (:func:`torrcast.stream._extra_mbit`) — и известна **одним числом на
    весь фильм**.

    Щуп пакует первые куски КОПИЕЙ — ровно тем, чем их положил бы показ, — и печатает три
    вещи на кусок: что обещала прикидка, что уехало на самом деле и куда после этого куска
    сдвинулась бы поправка (:meth:`torrcast.recode.Weights.calibrate`). Отсюда и виден
    ответ на оба вопроса карточки: врёт ли прикидка одинаково по всему фильму и на каком
    по счёту куске поправка перестаёт ходить.
    """
    media = probe(url)
    keys = film_keys(url)
    grid = grid_for(
        url,
        media.duration,
        step,
        True,
        say=lambda t: print(f"  {t}"),
        delivered_mbit=media.delivered_mbit,
        ceiling_mbit=config.recode_mbit if config.recode else 0.0,
        cap=profile.max_segment_bytes,
    )
    weights = Weights.of(keys, grid, delivered=media.delivered_mbit)
    if weights is None:
        print("карта без смещений - прикидки не будет")
        return
    print(
        f"источник: {url}\n"
        f"  {media.duration:.1f} с, {media.video}, доставляемый по паспорту "
        f"{media.delivered_mbit:.2f} Мбит/с\n"
        f"  средний по карте {weights.container:.2f} Мбит/с, поправка «контейнер → ТВ» "
        f"{weights.extra:.2f} Мбит/с (замеров {weights.measured})"
    )

    until = min(slot + count - 1, grid.count - 2)  # хвост в судьи не берём
    out = hls_dir(str(where))
    run = where / "run"
    from torrcast.stream import pack_start

    at = pack_start(url, grid.start(slot))
    command = ffmpeg_pack_command(url, 0, str(run), grid, slot, at, readrate=0.0, until=until)
    print(
        f"\nпакуем КОПИЕЙ v{slot}..v{until} (заход встанет на {at:.3f} с):\n  {' '.join(command)}"
    )
    packer = Packer.start(command, out, run, slot, last=until, at=at, grid=grid)
    began = time.monotonic()
    while packer.poll() is None and time.monotonic() - began < 1800:
        time.sleep(0.5)
    code = packer.poll()
    # 🔴 Взвешивается то, что ffmpeg НАПИСАЛ, а не то, что выкладка отдала наружу.
    # Разница не педантизм: тяжелее :data:`torrcast.stream.MAX_SEGMENT_BYTES` копия наружу
    # не выходит вовсе (:meth:`torrcast.stream.Packer.publish`), а щупу нужен именно её
    # вес - иначе ровно тот случай, ради которого щуп и заведён, из замера и выпадает.
    weighed = {s: p for p in run.glob("v*.ts") if slot <= (s := segment_slot(p.name)) <= until}
    print(f"копия v{slot}..v{until}: код возврата ffmpeg {code}, слово прогона: {packer.why()}")
    print(f"написано ffmpeg: {sorted(weighed) or 'ничего'}")

    print(
        f"\n{'кусок':<7}{'с':>6}{'сырьё':>8}{'прикидка':>10}{'обещано МБ':>12}"
        f"{'факт МБ':>9}{'промах':>9}{'extra после':>13}"
    )
    misses = []
    for number in range(slot, until + 1):
        path = weighed.get(number)
        if path is None:
            continue
        span = grid.span(number)
        got = path.stat().st_size
        due = weights.size(number, span)
        raw = weights.raw[number]
        guess = weights.at(number)
        miss = got / due - 1 if due > 0 else float("inf")
        misses.append((number, miss))
        weights.calibrate(number, got, span)
        print(
            f"v{number:<6}{span:>6.2f}{raw:>8.2f}{guess:>10.2f}{due / 2**20:>12.2f}"
            f"{got / 2**20:>9.2f}{miss * 100:>8.1f}%{weights.extra:>13.2f}"
        )
    packer.stop(reason="замер окончен")
    if not misses:
        print("ни одного куска не написано - сравнивать нечего")
        return
    first = misses[0][1]
    later = [m for _, m in misses[1:]] or [first]
    print(
        f"\nпромах на первом куске {100 * first:.1f}%, дальше "
        f"{100 * min(later):.1f}..{100 * max(later):.1f}% (кусков {len(later)})\n"
        f"поправка после {len(misses)} замеров: {weights.extra:.2f} Мбит/с "
        f"против {media.delivered_mbit:.2f} доставляемых по паспорту"
    )


def profile(url: str, size: int, step: float, threshold: float, extra: float) -> None:
    """Профиль тяжести фильма по карте опорных кадров."""
    print(f"файл: {url}\nразмер: {size / 2**30:.2f} ГиБ")
    grid, keys = _grid_of(url, step)
    weights = Weights.of(keys, grid, extra=extra)  # type: ignore[arg-type]
    if weights is None:
        print("карта без смещений - профиля не будет")
        return
    total = grid.duration
    print(f"\nпоправка «контейнер → ТВ»: {extra:.2f} Мбит/с (замерь --calibrate)")
    mean = sum(weights.at(s) * grid.span(s) for s in range(grid.count)) / total
    print(f"средний доставляемый: {mean:.2f} Мбит/с")
    for level in (12, 14, 15, 16, 18, 20):
        heavy = weights.heavy(float(level))
        seconds = sum(grid.span(s) for s in heavy)
        print(
            f"  >= {level:2} Мбит/с: {len(heavy):4} сегм. из {grid.count} "
            f"({seconds:5.0f} с, {100 * seconds / total:4.1f}% фильма)"
        )
    # Отдельное имя: выше `heavy` - кортеж от weights.heavy(), тут нужен набор
    # для проверок на вхождение, под одним именем типы не сходятся.
    heavy_slots = set(weights.heavy(threshold))
    runs, cur = [], None
    for slot in range(grid.count):
        if slot in heavy_slots:
            cur = [slot, slot] if cur is None else [cur[0], slot]
        elif cur:
            runs.append(tuple(cur))
            cur = None
    if cur:
        runs.append(tuple(cur))
    print(
        f"\nпри пороге {threshold:.0f}: серий подряд идущих тяжёлых {len(runs)}, "
        f"самая длинная {max((b - a + 1) for a, b in runs) if runs else 0} сегм."
    )
    print("топ-10 тяжёлых:")
    for slot in sorted(range(grid.count), key=lambda s: -weights.at(s))[:10]:
        print(
            f"  v{slot:<4} {grid.start(slot) / 60:6.2f} мин  span={grid.span(slot):5.2f} с  "
            f"{weights.at(slot):6.2f} Мбит/с"
        )


def plan(
    url: str, step: float, threshold: float, extra: float, rate: float, horizon: float
) -> None:
    """Модель показа: успевает ли кодировщик при скорости ``rate`` (× реального времени)."""
    grid, keys = _grid_of(url, step)
    weights = Weights.of(keys, grid, extra=extra)  # type: ignore[arg-type]
    assert weights is not None
    pending = list(weights.heavy(threshold))
    busy, late, worst, work = 0.0, 0, 0.0, 0.0
    while pending:
        ready = [s for s in pending if grid.start(s) <= busy + horizon]
        if not ready:
            busy = min(grid.start(s) for s in pending) - horizon
            continue
        slot = min(ready)
        pending.remove(slot)
        busy += grid.span(slot) / rate
        work += grid.span(slot) / rate
        if busy > grid.start(slot):
            late += 1
            worst = max(worst, busy - grid.start(slot))
    heavy = weights.heavy(threshold)
    print(f"скорость {rate:.2f}xRT, горизонт {horizon:.0f} с, порог {threshold:.0f} Мбит/с:")
    print(
        f"  тяжёлых {len(heavy)}, опоздали {late}, худшее опоздание {worst:.0f} с, "
        f"работы кодировщику {work / 60:.1f} мин на фильм {grid.duration / 60:.0f} мин"
    )


def dump(url: str, step: float, slot: int, count: int, where: Path) -> None:
    """Выложить несколько настоящих сегментов фильма на диск — вход для ``--speed``."""
    grid, _ = _grid_of(url, step)
    shutil.rmtree(where, ignore_errors=True)
    (where / "run").mkdir(parents=True)
    from torrcast.stream import pack_start

    at = pack_start(url, grid.start(slot))
    command = ffmpeg_pack_command(url, 0, str(where / "run"), grid, slot, at, readrate=0.0)
    packer = Packer.start(command, where, where / "run", slot, grid=grid)
    began = time.monotonic()
    while time.monotonic() - began < 900:
        packer.publish()
        if packer.edge >= slot + count - 1 or packer.poll() is not None:
            break
        time.sleep(0.5)
    packer.stop(keep_files=True, reason="хватит")
    made = sorted(where.glob("v*.ts"), key=lambda p: segment_slot(p.name))[:count]
    joined = where / "in.ts"
    with joined.open("wb") as sink:
        for piece in made:
            sink.write(piece.read_bytes())
    print(f"сложено {len(made)} сегментов в {joined} ({joined.stat().st_size / 2**20:.1f} МБ)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed", type=Path, help="замер скорости пресетов на готовом куске")
    parser.add_argument("--price", action="store_true", help="цена боевого тракта на источнике")
    parser.add_argument("--calibrate", action="store_true", help="прикидка тяжести против копии")
    parser.add_argument(
        "--profile",
        action="append",
        nargs="?",
        const="",
        metavar="КЛЮЧ",
        help="без ключа - профиль тяжести источника; с ключом - профиль приёмника; можно повторить",
    )
    parser.add_argument("--plan", action="store_true", help="модель показа для источника")
    parser.add_argument("--dump", action="store_true", help="выложить сегменты на диск")
    parser.add_argument("--film", help="источник - раздача в TorrServer (хеш)")
    parser.add_argument("--file", type=Path, help="источник - локальный файл (Range-раздача сама)")
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--where", type=Path, default=Path("/root/bench/seg"))
    parser.add_argument("--step", type=float, default=10.0)
    parser.add_argument("--threshold", type=float, default=15.0)
    parser.add_argument("--extra", type=float, default=0.0, help="поправка «контейнер → ТВ»")
    parser.add_argument("--at", type=float, default=1.4, help="скорость кодировщика, xRT")
    parser.add_argument("--mbit", type=float, default=0.0, help="потолок перекода, 0 - из настроек")
    parser.add_argument("--horizon", type=float, default=300.0)
    parser.add_argument("--json", type=Path, help="куда сложить профиль машиночитаемо")
    args = parser.parse_args()
    profiles = args.profile or []
    source_profile = "" in profiles
    receiver_profile = next((key for key in reversed(profiles) if key), None)
    config, choice = choose_profile(load_config(), receiver_profile)
    wants_source = args.price or args.calibrate or source_profile or args.plan or args.dump
    if wants_source and not (args.film or args.file):
        parser.error("нужен источник: --film ХЕШ или --file ПУТЬ")
    if args.speed:
        speed(args.speed)
    elif wants_source:
        url, size = _source(args.film, args.file)
        if args.price:
            price(url, args.slot, args.count, args.where, args.mbit, config, choice.profile)
        elif args.calibrate:
            calibrate(url, args.slot, args.count, args.where, args.step, config, choice.profile)
        elif source_profile:
            profile(url, size, args.step, args.threshold, args.extra)
        elif args.plan:
            plan(url, args.step, args.threshold, args.extra, args.at, args.horizon)
        else:
            dump(url, args.step, args.slot, args.count, args.where)
    else:
        parser.print_help()
    if args.json:
        args.json.write_text(json.dumps({"сделано": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
