#!/usr/bin/env python3
"""Замер: как часто раздача, которую запускает Enter, оказывается ПАКОМ.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/packprobe.py pools.jsonl
    python scripts/packprobe.py pools.jsonl --truth files.json
    python scripts/packprobe.py pools.jsonl --fetch http://127.0.0.1:8090 --out files.json

Отбор тут не переписан ни на строку: пул прогоняется
:func:`~poolreplay.replay`, то есть ровно тем же трактом, что и живой показ, а щуп
только смотрит, ЧТО у него получилось дефолтом и из чего этот дефолт состоит.

Меряется одно число и его населённость:

* сколько запросов вообще доехали до играбельной картины;
* у скольких из них дефолтная картина - вида ``movie``, то есть очереди серий у неё
  нет по построению (:func:`~torrcast.usecases.reinforce.plan_for.plan_for` заводит
  :class:`~torrcast.domain._series._Series` только виду ``tv``), и файл выбирается
  «самым крупным видеофайлом»;
* у скольких из них первый кандидат очереди похож на пак.

Похожесть на пак меряется двумя РАЗНЫМИ мерками, и путать их нельзя.

**По имени** (офлайн, ничего живого не нужно) - имя раздачи само говорит, что внутри
не одна картина: признак коллекции разбора
(:attr:`~torrcast.domain.release.Release.collection`) или серийные метки
(:attr:`~torrcast.domain.release.Release.kind` == ``tv``, линейка серий) у картины,
которую каталог считает фильмом. Это оценка СНИЗУ и только снизу: пак короткометражек,
чьё имя про сборник молчит, сюда не попадает вовсе - а он и есть больной случай.

**По файлам** (``--truth``) - доля самого крупного видеофайла в видеобайтах раздачи.
Ровно её и получает зритель: :func:`~torrcast.adapters.stream_probe.pick_video_file.pick_video_file`
берёт крупнейший. У одиночной картины доля близка к единице (рядом лежат сэмпл и
обложка), у пака из дюжины короткометражек - около доли одной части. Порога тут не
зашито: щуп печатает распределение, а где резать - решение продуктовое, не щупа.

Правда о файлах в репе не лежит и лежать не может - это выдача живого движка раздач.
Снимает её тот же щуп с ``--fetch``, и снимает боевым клиентом
(:class:`~torrcast.adapters.torrserver.torr_server.TorrServer`), а не своей копией.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import runpass
from poolreplay import Replay, batches_of, capped_of, replay
from probeprofile import add_argument as add_profile_argument
from probeprofile import choose as choose_profile

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.args import Args
from torrcast.domain.info_hash import info_hash
from torrcast.domain.infra_error import InfraError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.runtime.wire import wire
from torrcast.usecases.choice.first_alive import first_alive


@dataclass(slots=True)
class Pick:
    """Что Enter запустил бы по одному сохранённому пулу."""

    query: str
    picture: Picture
    release: Release
    #: Есть ли у плана очередь серий. У вида ``movie`` её нет по построению - и это
    #: ровно то место, где крупнейший файл становится единственным правилом выбора.
    queued: bool
    #: Хвост очереди ТОЙ ЖЕ картины: кем дефолт заменится, если его отбраковать.
    #: Картина у хвоста та же по построению, и это половина контрфакта: отбраковка
    #: внутри одной картины подменить картину не может физически.
    alternates: list[Release] = field(default_factory=list)

    @property
    def by_name(self) -> str:
        """Чем ИМЯ раздачи выдаёт пак; пусто - имя молчит."""
        if self.release.collection:
            return "коллекция"
        if self.release.kind == "tv":
            return "серийные метки"
        if len(self.release.episodes) > 1:
            return "линейка серий"
        return ""

    @property
    def at_risk(self) -> bool:
        """Картина, у которой очереди нет, а файл выбирается крупнейшим."""
        return not self.queued

    @property
    def pack_below(self) -> int:
        """Номер в очереди первой раздачи-сборника НИЖЕ дефолта; ноль - таких нет.

        🔴 Тем, что дефолт не сборник, дело не кончается, и мерить один дефолт значит
        мерить не тот случай. Очередь проходится дальше, когда рой молчит
        (:meth:`~torrcast.usecases.select.plan.Plan.candidates` отдаёт ВСЕ прошедшие
        ворота, а сдаётся показ по приговорам и по часам), - и вот на этом падении вниз
        сборник и становится тем, что играет. Ранжир его туда и ставит: он не
        выбрасывает сборник, а уводит его под одиночную раздачу.
        """
        return next((n for n, r in enumerate(self.alternates, start=2) if r.collection), 0)


def picks(items: list[Replay]) -> list[Pick]:
    """Дефолт каждого прогона: картина Enter и первый кандидат её очереди.

    Дефолт спрашивается той же меркой, что у показа (:func:`first_alive`), а очередь -
    боевым :meth:`~torrcast.usecases.select.plan.Plan.candidates`. Пустая очередь у
    дефолта невозможна по построению :func:`first_alive`, но проверяется: щуп, который
    молча пропускает свой предмет замера, мерить продукт не годится.
    """
    out: list[Pick] = []
    for item in items:
        if not item.plans:
            continue
        plan = item.plans[first_alive(item.plans) - 1]
        queue = plan.candidates(Args(query=item.query.split()))
        if not queue:
            continue
        out.append(
            Pick(
                query=item.query,
                picture=plan.picture,
                release=plan.ranked[queue[0] - 1],
                queued=plan.series is not None,
                alternates=[plan.ranked[n - 1] for n in queue[1:]],
            )
        )
    return out


def video_shares(files: list[list[Any]]) -> tuple[int, float]:
    """Сколько видеофайлов в раздаче и какая доля байтов у самого крупного.

    Считается по тем же расширениям, по которым видеофайл узнаёт показ
    (:data:`~torrcast.domain._name_data.data_3.VIDEO_EXT`).
    """
    sizes = [
        int(size) for name, size in files if str(name).lower().endswith(VIDEO_EXT) and int(size) > 0
    ]
    if not sizes:
        return (0, 0.0)
    return (len(sizes), max(sizes) / sum(sizes))


def named_in_corpus(items: list[Replay]) -> tuple[int, int]:
    """Сколько раздач ВСЕГО корпуса имя выдаёт коллекцией - и сколько их всего.

    🔴 Это отрицательная проба самого щупа, и без неё его ноль ничего не стоит. «Имя
    выдаёт пак: 0» читается двояко: либо имена и правда молчат, либо признак разбора не
    доехал и мерка мертва. Разводит эти два ответа только счёт по всему корпусу: если
    коллекции в нём находятся, а среди ДЕФОЛТОВ их нет, то ноль - это работа ранжира
    (сборник уступает одиночной раздаче), а не сломанный щуп.
    """
    seen = {
        id(release): release
        for item in items
        for picture in item.catalog
        for release in picture.releases
    }
    return (sum(1 for r in seen.values() if r.collection), len(seen))


def report(
    found: list[Pick], truth: dict[str, list[list[Any]]], items: list[Replay] | None = None
) -> list[str]:
    """Табличка замера и его итог."""
    risky = [p for p in found if p.at_risk]
    named = [p for p in risky if p.by_name]
    lines = [
        f"{'запрос':<34}{'вид':<7}{'очередь':<9}{'по имени':<16}{'доля':>6}  раздача",
    ]
    for pick in found:
        share = ""
        rows = truth.get(info_hash(pick.release))
        if rows is not None:
            count, biggest = video_shares(rows)
            share = f"{biggest:.2f}/{count}" if count else "-"
        lines.append(
            f"{pick.query[:33]:<34}{pick.picture.kind:<7}"
            f"{('серии' if pick.queued else 'нет'):<9}{(pick.by_name or '-'):<16}"
            f"{share:>6}  {pick.release.raw_name[:60]}"
        )
    lines += [
        "",
        f"запросов с играбельной картиной: {len(found)}",
        f"из них дефолт без очереди (файл = крупнейший): {len(risky)}",
        f"из них имя раздачи выдаёт пак: {len(named)}",
    ]
    below = [p for p in risky if p.pack_below]
    lines += [
        f"из них сборник стоит НИЖЕ дефолта, в той же очереди: {len(below)}",
        "  номер сборника в очереди по картинам: "
        + ", ".join(
            f"«{p.query}» №{p.pack_below}" for p in sorted(below, key=lambda p: p.pack_below)
        ),
        f"  очередь длиной 1 (падать некуда): {sum(1 for p in risky if not p.alternates)}",
    ]
    lines += below_truth(below, truth)
    if items is not None:
        marked, total = named_in_corpus(items)
        lines.append(
            f"отрицательная проба мерки имени: коллекций во всём корпусе {marked} из {total} раздач"
        )
    if truth:
        measured = [
            (pick, video_shares(truth[key]))
            for pick in risky
            if (key := info_hash(pick.release)) in truth
        ]
        alive = [(pick, seen) for pick, seen in measured if seen[0]]
        lines.append(
            f"из них правда о файлах снята: {len(alive)} (метаданных нет: "
            f"{len(risky) - len(alive)})"
        )
        for edge in (0.9, 0.7, 0.5):
            hit = [pick.query for pick, (_, share) in alive if share < edge]
            lines.append(f"  доля крупнейшего файла < {edge:.2f}: {len(hit)} {sorted(hit)}")
        lines += spread(alive)
        lines += counterfact([pick for pick, (_, share) in alive if share < 0.5])
    return lines


def below_truth(below: list[Pick], truth: dict[str, list[list[Any]]]) -> list[str]:
    """Правда о файлах тех сборников, что стоят ниже дефолта в очереди.

    Имя, назвавшее себя коллекцией, - ещё не пак: «Кинотрилогия» бывает и одним файлом
    склеенной части, и тремя. Спрашивается это ровно теми же долями, что и у дефолта, и
    отвечает на единственный вопрос, ради которого стоит трогать код: если показ до этой
    строки упадёт, зритель получит картину целиком или её двенадцатую часть.
    """
    if not below or not truth:
        return []
    seen = [
        (pick, video_shares(truth[key]))
        for pick in below
        if (key := info_hash(pick.alternates[pick.pack_below - 2])) in truth
    ]
    alive = [(pick, row) for pick, row in seen if row[0]]
    packs = [(pick, row) for pick, row in alive if row[1] < 0.5]
    return [
        f"  правда о них снята: {len(alive)} из {len(below)}",
        f"  из снятых и правда пак (доля < 0.50): {len(packs)}",
        *(
            f"    «{pick.query}» №{pick.pack_below}: доля {row[1]:.3f}, видеофайлов {row[0]}"
            for pick, row in sorted(alive, key=lambda row: row[1][1])
        ),
    ]


def spread(alive: list[tuple[Pick, tuple[int, float]]]) -> list[str]:
    """Разброс замера, а не только счёт за порогом.

    Порог - решение продуктовое, и щуп его не принимает. Но три числа под порогом
    печатать обязан: у скольких раздач видеофайл вообще один (пака там нет физически),
    какая доля самая низкая и у кого. Без разброса «ноль за порогом» читается как «мерили
    и не нашли», хотя разница между «0.99 у всех» и «0.51 у половины» - это разница между
    здоровым классом и классом, который вот-вот заболит.
    """
    if not alive:
        return []
    lone = [pick for pick, (count, _) in alive if count == 1]
    worst = min(alive, key=lambda row: row[1][1])
    counts = sorted(count for _, (count, _) in alive)
    return [
        f"  видеофайл в раздаче один: {len(lone)} из {len(alive)}",
        f"  видеофайлов в раздаче, медиана/максимум: {counts[len(counts) // 2]}/{counts[-1]}",
        f"  самая низкая доля: {worst[1][1]:.3f} у «{worst[0].query}» ({worst[1][0]} видеофайлов)",
    ]


def counterfact(packs: list[Pick]) -> list[str]:
    """Цена отбраковки пака: чем дефолт заменится и что при этом теряется.

    🔴 Мера обязана мерить ЦЕЛЬ, а цель тут - лестница продукта: русская дорожка выше
    чёткости. Поэтому считается не «сменился ли дефолт» (он сменится у всех по
    определению отбраковки), а что зритель на этой смене теряет: пропала ли русская
    дорожка, названная именем (:attr:`~torrcast.domain.release.Release.dubbed`), и просела
    ли высота кадра.

    Подмена картины тут вырасти не может, и это не надежда, а построение: хвост очереди
    взят у ТОГО ЖЕ плана, то есть у той же картины. Строка о нуле подмен всё равно
    печатается - молчание о контрфакте читается как «не мерили».
    """
    if not packs:
        return ["", "контрфакт: паков по этой мерке нет, менять нечего"]
    stranded = [p for p in packs if not p.alternates]
    swapped = [p for p in packs if p.alternates]
    lost_voice = [p for p in swapped if p.release.dubbed and not p.alternates[0].dubbed]
    lost_height = [p for p in swapped if p.alternates[0].height < p.release.height]
    return [
        "",
        f"контрфакт отбраковки пака (порог 0.5), затронуто картин: {len(packs)}",
        f"  замены нет вовсе, очередь кончилась: {len(stranded)} {[p.query for p in stranded]}",
        f"  дефолт сменился внутри той же картины: {len(swapped)}",
        f"  пропала русская дорожка, названная именем: {len(lost_voice)} "
        f"{[p.query for p in lost_voice]}",
        f"  просела высота кадра: {len(lost_height)} {[p.query for p in lost_height]}",
        "  подмен картины прибавилось: 0 (хвост очереди - та же картина по построению)",
    ]


def wanted(found: list[Pick]) -> list[tuple[str, Release]]:
    """Чьи файлы снимать: дефолт каждой картины и первый сборник НИЖЕ него.

    Второго мало не бывает: сборник, до которого показ падает на молчащем рое,
    отличается от дефолта ровно тем, что его никто не мерил. Пока снимали один дефолт,
    ответ «паков нет» был правдой про первую строку очереди и молчанием про остальные.
    """
    out: list[tuple[str, Release]] = []
    for pick in found:
        out.append((pick.query, pick.release))
        if pick.pack_below:
            out.append((f"{pick.query} #{pick.pack_below}", pick.alternates[pick.pack_below - 2]))
    return out


def fetch(
    base_url: str,
    found: list[Pick],
    seconds: float,
    known: dict[str, list[list[Any]]] | None = None,
) -> dict[str, list[list[Any]]]:
    """Снять список файлов по каждой раздаче замера живым движком раздач.

    Метаданные приходят по DHT, и приходят не всем: мёртвый рой молчит, и это ответ, а
    не сбой. Молчание записывается пустым списком - иначе перечитать прогон нечем.
    """
    engine = TorrServer(base_url)
    # Снятое прежде переспрашивать нечем: список файлов раздачи - свойство самой раздачи,
    # а не сегодняшнего роя. Зато доснять к нему соседей дешевле, чем снимать всё заново.
    out: dict[str, list[list[Any]]] = dict(known or {})
    asked = wanted(found)
    for number, (label, release) in enumerate(asked, start=1):
        key = info_hash(release)
        if not key or key in out:
            continue
        print(f"[{number}/{len(asked)}] {label}: {key}", file=sys.stderr)
        torrent_hash = ""
        try:
            torrent_hash = engine.add(release.magnet)
            files = engine.wait_files(torrent_hash, timeout=seconds)
            out[key] = [[f.name, f.size] for f in files]
        except (InfraError, OSError) as exc:
            print(f"    молчит: {exc}", file=sys.stderr)
            out[key] = []
        finally:
            # Замер за собой прибирает: движок раздач - общий стенд, и оставленная им
            # сотня раздач достаётся следующему замеру чужим кэшем и чужими пирами.
            if torrent_hash:
                engine.drop(torrent_hash)
    return out


def main(argv: list[str] | None = None) -> int:
    # Тракт отбора сценарию раздаёт композиционный корень - как и всем щупам отбора.
    wire()
    ap = argparse.ArgumentParser(description="как часто дефолтная раздача оказывается паком")
    ap.add_argument("pools", type=Path, help="pools.jsonl со снятыми выдачами индексеров")
    ap.add_argument("--truth", type=Path, help="снятые списки файлов: {инфохэш: [[имя, размер]]}")
    ap.add_argument("--fetch", metavar="URL", help="снять списки файлов живым движком раздач")
    ap.add_argument("--out", type=Path, help="куда положить снятое (--fetch)")
    ap.add_argument("--wait", type=float, default=60.0, help="сколько ждать метаданные, секунд")
    add_profile_argument(ap)
    args = ap.parse_args(argv)
    cmdline = list(argv) if argv is not None else sys.argv[1:]

    config, choice = choose_profile(load_config(), args.profile)
    items: list[Replay] = []
    for line in args.pools.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        items.append(
            replay(
                str(record.get("query", "")),
                batches_of(record),
                config,
                choice.profile,
                capped_of(record),
            )
        )

    found = picks(items)
    truth: dict[str, list[list[Any]]] = {}
    if args.truth is not None:
        truth = json.loads(args.truth.read_text(encoding="utf-8"))
    if args.fetch:
        taken = fetch(args.fetch, [p for p in found if p.at_risk], args.wait, truth)
        if args.out:
            args.out.write_text(json.dumps(taken, ensure_ascii=False), encoding="utf-8")
            card = runpass.passport("packprobe", [args.pools], cmdline)
            print(f"\n{runpass.told(card)}\nпаспорт прогона: {runpass.write(card, args.out)}")
        return 0

    print("\n".join(report(found, truth, items)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
