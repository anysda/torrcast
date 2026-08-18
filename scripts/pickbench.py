"""Секундомер ФАЗЫ ОТБОРА: во что человеку обходится брак верхнего релиза (TC-120).

Меряется ровно то, что видно глазами после ответа на меню: сколько идёт
:meth:`torrcast.Bench.resolve` - от «картина выбрана» до «отбор релиза». Индексеры при
этом не спрашиваются вовсе: план собирается из magnet-ссылок, названных в командной
строке, поэтому замер не жжёт квоту трекеров и повторяется одинаково.

    python3 scripts/pickbench.py --magnets m1 m2 --filler m3 m4 --think 8 --runs 3

``--magnets`` - два релиза ОДНОЙ картины: первый пойдёт верхом, второй запасным.
``--filler`` - соседние картины франшизы: они занимают остальные места прогрева под меню
(:data:`torrcast.PREWARM`), то есть воспроизводят настоящую конкуренцию за рой.
``--ceiling`` - потолок отбраковки, Мбит/с: между настоящими битрейтами двух релизов он
даёт сценарий «верх забракован», выше обоих - «верх годен».

⚠️ Телевизор не участвует: показ не запускается, дело кончается выбранным релизом. Всё
поднятое убирается из TorrServer ПО ЯВНЫМ ХЭШАМ - списком сервер чистить нельзя, потому
что в списке лежат ЧУЖИЕ раздачи. Свои в нём как раз видны (проверено на TorrServer
MatriX.142.2), но пропадают после перезапуска службы: заведены с ``save_to_db: false``.

Своё состояние (кэш карт опорных кадров) замер держит в :data:`BENCH` и чистит перед
каждым прогоном: без этого второй прогон читал бы карту из кэша первого и был бы теплее.
Рабочее состояние при этом не трогается вовсе.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast import TorrcastError
from torrcast.adapters.console.console import Progress
from torrcast.adapters.filesystem.state import load_config, state_path
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.args import Args
from torrcast.domain.picture import Picture
from torrcast.domain.prewarm_settings import PREWARM
from torrcast.domain.release import Release
from torrcast.runtime.wire import wire
from torrcast.usecases.choice import warm_order
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench

#: Каталог замера: своё состояние и свой кэш карт, рабочие не трогаются. Живёт во
#: временном каталоге системы: замер не вправе требовать ни root, ни чужой машины.
BENCH = Path(tempfile.gettempdir()) / "torrcast-pickbench"
GB = 1024**3


def release(magnet: str, number: int, seeders: int = 100) -> Release:
    """Синтетическое имя на настоящий magnet: разбор имён тут не проверяется.

    ⚠️ Размер тут - заявка ИМЕНИ, и нужен он ровно для того, чтобы релиз прошёл в очередь
    (:func:`torrcast.usecases.rank.is_candidate` прикидывает битрейт по нему). Приговор выносится не
    по нему, а по прочитанному файлу: настоящий вес считает ffprobe уже в отборе, и именно
    он решает, забракован верх или годен.
    """
    return Release(
        raw_name=f"Кино {number} / Movie {number} (1999) WEB-DL 1080p H.264",
        title=f"Кино {number}",
        year=1999,
        quality="1080p",
        codec="H.264",
        size=2 * GB,
        seeders=seeders,
        magnet=magnet,
    )


def plans(magnets: list[str], filler: list[str], ceiling: float) -> list[Plan]:
    """Картина под замером и её соседи по франшизе - ровно то, что греется под меню."""
    made: list[Plan] = []
    for spot, group in enumerate([magnets, *[[m] for m in filler]]):
        ranked = [release(m, n) for n, m in enumerate(group, start=1)]
        picture = Picture(title=f"Кино {spot + 1}", year=1999 + spot, releases=ranked)
        made.append(Plan(picture=picture, ranked=ranked, runtime=6000.0, warn_mbit=ceiling))
    return made


def once(url: str, order: list[Plan], think: float, spare: bool) -> tuple[float, str]:
    """Один прогон: прогрев под меню, пауза «человек читает», отбор. Всё убирается за собой."""
    shutil.rmtree(state_path().parent / "keys", ignore_errors=True)  # старт холодный
    bench = Bench(TorrServer(url))
    args = Args(query=["кино"])
    warmed = warm_order(order)
    for plan in warmed[:PREWARM]:
        if queue := plan.candidates(args):  # голова очереди, как на боевом пути (TC-432)
            bench.start(plan, queue[0])
    if spare:  # правка TC-120: запасной релиз выбранной картины греется тут же
        bench.spare(warmed[0], args)
    time.sleep(think)  # человек читает меню и жмёт Enter
    picked = time.monotonic()
    note = ""
    try:
        with Progress(out=io.StringIO()) as progress:
            prep = bench.resolve(warmed[0], args, progress)
        note = f"релиз {prep.number}"
    except TorrcastError as exc:
        note = f"отказ: {exc}"
    spent = time.monotonic() - picked
    bench.drop_all()  # по явным хэшам: чистка списком снесла бы и чужие раздачи
    return spent, note


def weigh(url: str, magnet: str) -> str:
    """Настоящий вес релиза: что скажет ffprobe о файле, который поднят из этого magnet."""
    from torrcast.adapters.stream_probe.pick_video_file import pick_video_file
    from torrcast.adapters.stream_probe.probe import probe

    torrserver = TorrServer(url)
    torrent_hash = torrserver.add(magnet)
    try:
        video = pick_video_file(torrserver.wait_files(torrent_hash, timeout=60.0))
        media = probe(torrserver.stream_url(torrent_hash, video.index), timeout=60.0)
        return f"{video.name}: {media.weight_mbit(video.size):.1f} Мбит/с, {media.video}"
    finally:
        torrserver.drop(torrent_hash)


def main() -> int:
    # Тракт отбора сценарию раздаёт композиционный корень: без него первый же
    # вопрос сценария внешнему миру падает на несобранной среде.
    wire()
    ap = argparse.ArgumentParser()
    ap.add_argument("--magnets", nargs=2, required=True, help="верх и запасной одной картины")
    ap.add_argument("--filler", nargs="*", default=[], help="соседние картины франшизы")
    ap.add_argument("--ceiling", type=float, default=1000.0, help="потолок отбраковки, Мбит/с")
    ap.add_argument("--think", type=float, default=8.0, help="сколько человек читает меню, с")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--spare", action="store_true", help="греть запасной под меню (TC-120)")
    ap.add_argument("--weigh", action="store_true", help="только измерить вес магнитов")
    args = ap.parse_args()

    BENCH.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TORRCAST_STATE", str(BENCH / "state.json"))
    url = load_config().torrserver_url
    if args.weigh:
        for magnet in [*args.magnets, *args.filler]:
            with contextlib.suppress(TorrcastError):
                print(weigh(url, magnet))
        return 0

    spent: list[float] = []
    for run in range(1, args.runs + 1):
        order = plans(list(args.magnets), list(args.filler), args.ceiling)
        took, note = once(url, order, args.think, args.spare)
        spent.append(took)
        print(f"прогон {run}: отбор {took:.1f} с - {note}", flush=True)
        time.sleep(5.0)  # рою дают отпустить снятые раздачи
    spread = f"{min(spent):.1f}-{max(spent):.1f}"
    print(f"\nотбор: медиана {statistics.median(spent):.1f} с, разброс {spread} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
