"""Журнал приёмника за окно замера и признак того, что прибор всё это время был жив.

Живой замер считают ДВА независимых прибора: наша лента следа говорит, что мы приёмнику
отдали, а его журнал - что он с этим сделал. Второй прибор молчаливый: оборванный поток
выглядит ровно как спокойный показ, и обе половины меры дают тогда один и тот же ноль -
только один заработанный, а другой купленный.

    python3 scripts/tvjournal.py 10.0.0.5:5555 --seconds 300 --out прогон/logcat.txt

🔴 Ноль голоданий засчитывается ТОЛЬКО живому журналу: прогон с оборванным журналом -
это БРАК замера, а не чистый показ. Признак тут не затыкает вторую половину меры, а
требует её - нет журнала, нет и ответа про голодания.

🔴 Поток рвётся не по нашей воле: перезапуск локального демона отладки убивает клиента,
а приёмник об этом даже не знает, и замер одной командой ``logcat`` слепнет молча.
Поэтому щуп держит журнал сам (:func:`follow`), а число подъёмов печатает: молчаливо
пережитый обрыв - тоже улика.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import runpass

#: Метка строки журнала в виде ``epoch``: секунды с эпохи прямо в строке.
#:
#: 🔴 Формат выбран НЕ для красоты. Привычный ``threadtime`` печатает местное время
#: ПРИЁМНИКА и без года: стоят они в разных поясах сплошь и рядом, и тогда признак
#: сравнивает двое разных часов - журнал уезжает на часы мимо окна. У ``epoch`` пояса нет.
STAMP = re.compile(rb"^\s*(\d{9,})\.(\d{3})\b")

#: Худшая тишина ЖИВОГО журнала: четыре прогона по 300 с на приёмнике дали 3.013-3.015 с,
#: и тишина эта НАША - столько стоит поднять оборванный поток заново и продолжить с метки.
SILENCE_LIVE = 3.02

#: Самая КОРОТКАЯ тишина ослепшего журнала из всех замеренных: 155.9 с (21 прогон, разброс
#: до 431.9 с; наивный читатель в тот же день на том же приёмнике дал 277.1 и 295.6 с).
SILENCE_BLIND = 155.9

#: Самая длинная тишина, которую живой журнал приёмника считает своей.
#:
#: 🔴 Порог МЕРЯН с обеих сторон и лежит между :data:`SILENCE_LIVE` и :data:`SILENCE_BLIND`
#: - это и проверяет зеркало щупа. Внутри промежутка он посажен близко к живому краю
#: (вшестеро выше живой тишины и вдесятеро ниже самой тесной ослепшей), потому что цена
#: двух ошибок разная: лишний БРАК стоит повторного прогона, а пропущенная слепота -
#: ложного нуля в отчёте, который уже не отличить от заработанного.
#:
#: 🔴 Считать живость СТРОКАМИ нельзя, и это тоже замер, а не осторожность: прежний признак
#: «строк не меньше пятисот» засчитывал годными прогоны, чей журнал жил секунду из
#: четырёхсот. На том же приёмнике МЁРТВЫЙ читатель дал 10203 строки, а ЖИВОЙ - 1873:
#: строк у ослепшего прибора впятеро больше, потому что он вываливает кольцевой буфер.
SILENCE = 20.0

#: Сколько ждать ответа коротких команд отладчика, секунды.
TALK = 30.0


@dataclass(frozen=True)
class Held:
    """Окно, которое читатель журнала продержал, и сколько раз поднимал поток.

    Окно называет САМ читатель: судить журнал надо отрезком, на котором прибор обязан был
    писать, иначе в меру заезжает время сборов.
    """

    raised: int
    began: float
    ended: float


@dataclass(frozen=True)
class Life:
    """Что журнал говорит о СЕБЕ: покрыл ли он окно замера и где в нём молчал."""

    lines: int
    stamped: int
    #: Самая долгая тишина внутри окна вместе с краями: от начала прогона до первой
    #: метки и от последней метки до конца. Оборванный журнал виден именно здесь.
    silence: float
    #: На сколько первая метка журнала опережает начало прогона. Заметно больше нуля -
    #: журнал несёт не наш прогон, а кольцевой буфер, накопленный ДО него.
    backlog: float
    fit: bool
    why: str


def stamps(text: bytes) -> list[float]:
    """Метки строк журнала как время. Пояса тут нет по построению (:data:`STAMP`)."""
    found = []
    for line in text.splitlines():
        mark = STAMP.match(line)
        if mark is not None:
            found.append(int(mark.group(1)) + int(mark.group(2)) / 1000)
    return found


def life(began: float, ended: float, text: bytes, silence: float = SILENCE) -> Life:
    """Судить журнал по ОКНУ ЗАМЕРА, а не по объёму: жив тот, кто не молчал дольше срока.

    🔴 Пустой журнал - брак, а не «событий не было»: нечитанный прибор не чистый показ.
    """
    lines = len([line for line in text.splitlines() if line.strip()])
    marks = stamps(text)
    if not marks:
        return Life(lines, 0, ended - began, 0.0, False, "журнал без меток - прибор не читан")
    backlog = max(0.0, began - min(marks))
    inside = sorted(mark for mark in marks if began <= mark <= ended)
    if not inside:
        return Life(lines, len(marks), ended - began, backlog, False, "журнал не об этом прогоне")
    edges = [inside[0] - began, ended - inside[-1]]
    holes = [second - first for first, second in pairwise(inside)]
    worst = max(edges + holes)
    if backlog > silence:
        why = f"журнал начат за {backlog:.1f} с до прогона - это кольцевой буфер, не замер"
        return Life(lines, len(marks), worst, backlog, False, why)
    if worst > silence:
        # Оба замеренных края названы вслух не для красоты: по одному числу «молчал 277 с»
        # не видно, это край нормы или полная слепота, а решение по прогону принимают люди.
        like = ", столько молчит ОСЛЕПШИЙ прибор" if worst >= SILENCE_BLIND else ""
        why = f"журнал молчал {worst:.1f} с при пороге {silence:.1f} с{like} - ослеп посреди"
        return Life(lines, len(marks), worst, backlog, False, why)
    ours = " - это наш подъём потока" if worst <= SILENCE_LIVE else ""
    why = f"журнал жив, худшая тишина {worst:.1f} с{ours}"
    return Life(lines, len(marks), worst, backlog, True, why)


def _talk(*command: str) -> None:
    """Короткая команда отладчика; отказ не приговор - следующий заход попробует снова."""
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
        try:
            proc.wait(timeout=TALK)
        except subprocess.TimeoutExpired:
            proc.kill()


def follow(device: str, out: Path, seconds: float) -> Held:
    """Держать журнал открытым всё окно и назвать его вместе с числом подъёмов потока.

    Продолжение идёт с последней метки (``-T``): дыры переподключение не оставляет, а
    строки, повторно отданные той же меткой, отсеиваются по тексту.
    """
    began = time.time()
    deadline = time.monotonic() + seconds
    resume, seen, raised = "", set[bytes](), 0
    with out.open("wb") as sink:
        while time.monotonic() < deadline:
            raised += 1
            _talk("adb", "connect", device)
            command = ["adb", "-s", device, "logcat", "-v", "epoch"]
            command += ["-T", resume] if resume else []
            if not resume:
                _talk("adb", "-s", device, "logcat", "-c")
            with subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            ) as proc:
                killer = threading.Timer(max(0.0, deadline - time.monotonic()), proc.kill)
                killer.start()
                for line in proc.stdout or ():
                    if line in seen:
                        continue
                    sink.write(line)
                    sink.flush()
                    mark = STAMP.match(line)
                    if mark is not None:
                        # Метку продолжения ``-T`` отладчик принимает голой: слева у
                        # неё в журнале стоят пробелы выравнивания.
                        found = line[: mark.end()].decode().strip()
                        if found != resume:
                            resume, seen = found, set()
                        seen.add(line)
                killer.cancel()
    return Held(raised, began, time.time())


#: Чем читается журнал. Умолчание боевое, замеру признака подставляют готовый журнал.
Follow = Callable[[str, Path, float], Held]


def main(follow: Follow = follow) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", help="приёмник для отладчика, например 10.0.0.5:5555")
    parser.add_argument("--seconds", type=float, required=True, help="окно замера")
    parser.add_argument("--out", type=Path, required=True, help="куда писать журнал")
    parser.add_argument("--silence", type=float, default=SILENCE, help="порог тишины, с")
    parser.add_argument("--count", default="DEMUXER_UNDERFLOW", help="что считать в журнале")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    held = follow(args.device, args.out, args.seconds)
    text = args.out.read_bytes()
    told = life(held.began, held.ended, text, args.silence)
    # Годность едет ВМЕСТЕ с журналом, а не только в консоль: прочитанный через месяц
    # файл обязан сам говорить, был ли прибор жив, когда его писали.
    runpass.write(
        runpass.passport("tvjournal", [], sys.argv[1:], fit=runpass.Fit(told.fit, told.why)),
        args.out,
    )
    print(
        f"журнал: {told.lines} строк, меток {told.stamped}, "
        f"поток поднимался {held.raised} раз, "
        f"худшая тишина {told.silence:.1f} с при пороге {args.silence:.1f} с"
    )
    if not told.fit:
        # 🔴 Счёт голоданий тут НЕ печатается вовсе, и это главное: ноль на мёртвом
        # приборе неотличим от нуля на чистом показе, а прочитанный ноль уезжает в отчёт.
        print(f"БРАК ЗАМЕРА: {told.why}", file=sys.stderr)
        return 1
    print(f"ГОДЕН: {told.why}; {args.count} за прогон: {text.count(args.count.encode())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
