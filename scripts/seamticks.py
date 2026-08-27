#!/usr/bin/env python3
"""Меряет стык звука между соседними кусками показа в ТИКАХ дорожки, а не в секундах.

    python3 scripts/seamticks.py --head init.mp4 v0.m4s v1.m4s v2.m4s
    python3 scripts/seamticks.py --head cp/init.mp4 --head-of 1=spare/head1.mp4 v0.m4s v1.m4s

🔴 Метки показа для этого не годятся. У куска, несущего свой список правок, СВОЯ точка
отсчёта, и наивная разность соседних меток даёт заведомую чушь - заход через них дал -13 и
-37 секунд. Тики же лежат в самом фрагменте: ``baseMediaDecodeTime`` называет, с какого
тика дорожки кусок начинается, а сумма длительностей сэмплов - сколько тиков он занимает.
Обе величины абсолютны и списка правок не знают вовсе. Стык = начало следующего минус
конец предыдущего; ноль - сплошной звук.

⚠️ Длину кадра щуп НЕ знает заранее, а читает частоту из потока. Кадр AAC - это 1024
сэмпла, и в тиках он равен 1024 только пока шкала дорожки равна частоте: на 48 кГц при
шкале 90 кГц тот же кадр - 1920 тиков. Прибор, у которого длина кадра зашита числом, на
каталоге с 44.1 кГц читает сплошной звук как десятки отдельных прогонов с дырами.

⚠️ Голый кусок CMAF (``moof mdat``) не открывается ничем: ``trun track id unknown``. Кусок
подаётся ffprobe вместе со своим заголовком, а несёт ли он его уже сам - щуп спрашивает у
продукта (:func:`torrcast.domain.cmaf_body.cmaf_body`), а не решает по расширению.

На stdout идёт JSONL: строка на кусок, строка на стык, затем итог.
Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Щуп зовёт продукт и обязан звать СВОЙ: editable-установка венва смотрит на соседний
# клон, и без этой строки замер снимался бы кодом, который правят в чужой работе.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.domain.cmaf_body import cmaf_body

#: Сколько сэмплов в кадре AAC. Число не наше и не настраивается: так устроен кодек.
SAMPLES_PER_FRAME = 1024

#: Сколько байт от начала куска хватает, чтобы увидеть, несёт ли он свой заголовок.
HEAD_PEEK = 64 << 10

#: Сколько ждать ffprobe на одном куске, секунды.
TIMEOUT = 60.0


class ProbeError(RuntimeError):
    """Кусок не прочитался: мерить по нему нечего, и молчать об этом нельзя."""


@dataclass(frozen=True)
class Span:
    """Один кусок в тиках своей дорожки: откуда начался, где кончился, сколько кадров."""

    name: str
    first: int
    end: int
    frames: int
    scale: int
    rate: int

    @property
    def per_frame(self) -> int:
        """Длина кадра AAC в тиках ЭТОЙ дорожки: 1024 сэмпла, пересчитанные в её шкалу."""
        return SAMPLES_PER_FRAME * self.scale // self.rate if self.rate else 0


def feed(chunk: Path, head: Path | None) -> str:
    """Чем открыть кусок: голый фрагмент читается только вместе со своим заголовком."""
    if head is None:
        return str(chunk)
    carried = cmaf_body(chunk.open("rb").read(HEAD_PEEK))
    return str(chunk) if carried != 0 else f"concat:{head}|{chunk}"


def _ask(what: str, target: str, stream: bool, timeout: float) -> str:
    command = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", f"{'stream' if stream else 'packet'}={what}",
        "-of", "csv=p=0", target,
    ]  # fmt: skip
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if done.returncode != 0:
        raise ProbeError(done.stderr.strip().splitlines()[-1] if done.stderr else "ffprobe молчит")
    return done.stdout


def track(target: str, timeout: float = TIMEOUT) -> tuple[int, int]:
    """Шкала дорожки и частота её звука - обе из потока, обе нужны для длины кадра."""
    raw = _ask("time_base,sample_rate", target, True, timeout).strip().splitlines()
    if not raw:
        raise ProbeError("у куска нет звуковой дорожки")
    parts = raw[0].split(",")
    base = next((p for p in parts if "/" in p), "")
    rate = next((p for p in parts if p.isdigit()), "")
    if not base or not rate:
        raise ProbeError(f"ffprobe не назвал шкалу и частоту: {raw[0]!r}")
    return int(base.split("/")[1]), int(rate)


def packets(target: str, timeout: float = TIMEOUT) -> list[tuple[int, int]]:
    """Сэмплы куска парами «тик начала, длительность»; пропущенные метки не считаются."""
    out = []
    for line in _ask("dts,duration", target, False, timeout).splitlines():
        dts, _, dur = line.partition(",")
        if dts.strip("- ").isdigit() and dur.strip("- ").isdigit():
            out.append((int(dts), int(dur)))
    return out


def span(name: str, rows: list[tuple[int, int]], scale: int, rate: int) -> Span:
    """Границы куска в тиках: первый тик и тик СРАЗУ ЗА последним сэмплом.

    Конец берётся по последнему сэмплу, а не по первому плюс длина: муксер бывает и
    неровен, а стык меряется ровно там, где кончаются байты.
    """
    if not rows:
        raise ProbeError("в куске нет ни одного сэмпла звука")
    last = max(rows, key=lambda one: one[0])
    return Span(name, min(one[0] for one in rows), last[0] + last[1], len(rows), scale, rate)


def seam(before: Span, after: Span) -> int:
    """Стык в тиках: ноль - звук сплошной, плюс - дыра, минус - метки назад."""
    return after.first - before.end


def measure(chunks: list[Path], head: Path | None, heads: dict[int, Path]) -> list[Span]:
    """По куску на каждый кусок, в порядке сетки: где он начался и где кончился."""
    out = []
    for number, chunk in enumerate(chunks):
        target = feed(chunk, heads.get(number, head))
        scale, rate = track(target)
        out.append(span(chunk.name, packets(target), scale, rate))
    return out


def report(spans: list[Span]) -> dict[str, object]:
    """Итог: сколько стыков нулевые, где самый широкий и чем он равен в кадрах."""
    seams = [seam(a, b) for a, b in itertools.pairwise(spans)]
    per_frame = spans[0].per_frame if spans else 0
    widest = max(seams, key=abs) if seams else 0
    return {
        "кусков": len(spans),
        "стыков": len(seams),
        "нулевых": sum(1 for one in seams if one == 0),
        "самый широкий, тиков": widest,
        "самый широкий, кадров": round(widest / per_frame, 3) if per_frame else None,
        "кадр, тиков": per_frame,
        "шкала": spans[0].scale if spans else None,
        "частота": spans[0].rate if spans else None,
        "стык звука нулевой": bool(seams) and all(one == 0 for one in seams),
    }


def _pairs(given: list[str]) -> dict[int, Path]:
    out = {}
    for one in given:
        number, _, path = one.partition("=")
        out[int(number)] = Path(path)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seamticks", description=__doc__)
    parser.add_argument("chunks", nargs="+", type=Path, help="куски в порядке сетки")
    parser.add_argument("--head", type=Path, help="общий заголовок показа")
    parser.add_argument(
        "--head-of", action="append", default=[], metavar="N=ПУТЬ",
        help="свой заголовок куску N (нумерация с нуля, по порядку доводов)",
    )  # fmt: skip
    args = parser.parse_args(argv)
    try:
        spans = measure(args.chunks, args.head, _pairs(args.head_of))
    except (ProbeError, OSError, subprocess.SubprocessError) as boom:
        print(json.dumps({"отказ": str(boom)}, ensure_ascii=False))
        return 2
    for one in spans:
        print(json.dumps({
            "кусок": one.name, "первый тик": one.first, "конец": one.end,
            "кадров": one.frames, "кадр, тиков": one.per_frame,
        }, ensure_ascii=False))  # fmt: skip
    for before, after in itertools.pairwise(spans):
        gap = seam(before, after)
        print(json.dumps({
            "стык": f"{before.name} - {after.name}", "тиков": gap,
            "кадров": round(gap / before.per_frame, 3) if before.per_frame else None,
        }, ensure_ascii=False))  # fmt: skip
    print(json.dumps(report(spans), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
