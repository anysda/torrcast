"""🔴 TC-909. Полоса установщика не вправе обгонять сделанную работу.

TC-885 сторожит связь «полоса <-> счётчик фаз» и переживает перенос `phase_done`
с `job_wait` на `job_start`: формула та же, различных значений столько же, сотня
в конце на месте. Здесь сторожится вторая половина цепи, которую не мерил никто:
«счётчик фаз <-> сделанная работа».

Стенд - сам install.sh, у которого подменены РАБОТНИКИ, а проводка `main`
(`job_start`, `job_wait`, `phase_done`) не тронута ни на символ. Долгая фаза
отмечает своими часами начало и конец СВОЕЙ работы, рисовалка пишет след
покадрово, и обе линии сверяются по одним и тем же миллисекундам эпохи.

⚠️ След ставит кадру момент, снятый в конце ПРЕДЫДУЩЕГО кадра, поэтому у
абсолютных сверок есть допуск :data:`LAG_FRAMES` - квантование прибора, а не
подгонка. Плато же меряется РАЗНОСТЬЮ двух отметок следа, в которой этот сдвиг
сокращается, поэтому у главной сверки допуска нет вовсе.

🔴 TC-922. Здесь же закрыты две слепоты самого сторожа, найденные встречной пробой.

Первая: сверки были односторонними, против ОПЕРЕЖЕНИЯ. Деление, взятое сильно
позже своей работы, проходило зелёным всегда, а человеку это видно как замершая
полоса и прыжок через два деления. Теперь у каждой сверки две стороны
(:func:`_out_of_step`), и поздняя сторона меряется не «концом своей работы», а
моментом, РАНЬШЕ которого доложить было нечего: фазы идут параллельно, `main`
закрывает их по очереди, и фаза, чья работа кончилась первой, честно ждёт своей
очереди (TorrServer в честном прогоне берёт деление через ~1 с после конца своей
работы - за ffmpeg, стоящим в очереди перед ним).

Вторая: номер деления держался жёсткой таблицей «фаза -> номер», а порядок
делений задаёт порядок вызовов `phase_done` в `main`. Перестановка уводила замер
на чужую фазу молча. Теперь номер берётся ИЗ ПРОГОНА: полоса пишет в след строку
`CLOSE done=N phase=имя` на каждое закрытие - ровно ту пару, которую человек
читает в строке статуса, - а связь «имя <-> работа» держит якорь
:func:`_mislabelled`, сверяющий подпись каждой фазы с её блоком в `main`.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import struct
import subprocess
import termios
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import pytest

REPO = Path(__file__).parents[1]
SCRIPT = (REPO / "install.sh").read_text(encoding="utf-8")

#: Длина кадра рисовалки, мс. Ею плато переводится из миллисекунд в кадры.
#: Читается из самого `install.sh`: вписанная руками копия молча разъезжается с
#: источником, и тогда мера переводит время в кадры по числу, которого в
#: продукте уже нет.
FRAME_MS = int(re.search(r"^FRAME_MS=(\d+)$", SCRIPT, re.M).group(1))  # type: ignore[union-attr]
#: Допуск абсолютных сверок: сдвиг следа на кадр плюс запас на лаг планировщика.
#: Он вчетверо меньше самого короткого опережения, которое мера обязана поймать
#: (1.0 с у `источников`), поэтому ослабить сторож не может.
LAG_FRAMES = 3
ROWS, COLS = 34, 110
ENTRY = "# --- Точка входа ---"
SYNC_ON = "\x1b[?2026h"
SYNC_OFF = "\x1b[?2026l"
CYRILLIC = re.compile(r"[\u0400-\u052f\u1c80-\u1c8f\u2de0-\u2dff\ua640-\ua69f\ufe2e-\ufe2f]+")
#: 🔴 TC-948. Единственная кириллица, законная в английском кадре: подпись двери в
#: русский. Дверь обязана быть названа ТЕМ языком, в который ведёт, иначе она не
#: дверь, а загадка. Вырезается ровно эта пара «ключ + подпись», поэтому любое
#: другое русское слово в английской заставке сторож ловит как ловил. Чтобы вырез
#: не стал слепым пятном, сама дверь ниже проверяется на присутствие.
LANG_DOOR = re.compile(r"cast --ru\s+русский")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

#: Стенд плато: одна долгая фаза. Две передние закрываются ДО запуска заданий,
#: поэтому деление, на котором полоса обязана стоять, - середина шкалы.
SLOW_S = 3.0
#: Передняя фаза работает заметное время НЕ для красоты: иначе левый край плато
#: упирается не в начало работы, а в запуск самого прибора - рисовалка выходит
#: на кадры позже, чем `main` доходит до `job_start`, и плато выглядит короче
#: работы на эту разницу.
WARMUP_S = 0.4
HOLD_PHASES = "locale packages ffmpeg torrserver"
HOLD_WORK = {"install_packages": WARMUP_S, "install_ffmpeg": SLOW_S}
#: Сколько фаз закрыто к началу работы долгой фазы и сколько их всего.
BEFORE, HOLD_TOTAL = 2, 4

#: Стенд всех фоновых фаз: задания идут параллельно, поэтому прогон стоит не
#: суммы, а самой долгой из них.
ALL_PHASES = "locale packages ffmpeg torrserver sources prowlarr"
ALL_WORK = {
    "install_packages": WARMUP_S,
    "check_sources": 1.0,
    "install_prowlarr": 1.5,
    "install_torrserver": 2.0,
    "install_ffmpeg": SLOW_S,
}
ALL_TOTAL = 6
#: Стенд запаздывания: TorrServer работает ДОЛЬШЕ ffmpeg, и подделка ниже
#: заставляет доклад ffmpeg ждать его. Честному прогону такой стенд не нужен -
#: он поднимается только отрицательной пробой.
LATE_WORK = {**HOLD_WORK, "install_torrserver": 4.5}


class Label(NamedTuple):
    """Пара подписей одной фазы: та же работа на двух языках заставки."""

    en: str
    ru: str


#: 🔴 Подпись, которой фаза закрывается в `main`, - аргументы `phase_done` и ровно
#: те слова, которые человек читает в строке статуса («фаза 3/6: источники»,
#: «phase 3/6: sources»). Номеров деления в таблице НЕТ: их называет сам прогон,
#: поэтому перестановка вызовов `phase_done` больше не уводит замер на чужую фазу.
#: 🔴 TC-1052. Языков в паре два, и это не удобство таблицы. Английской ветке в
#: канал уходил литерал `installation` на все двенадцать закрытий: опознавать было
#: нечего (0 фаз из 12), поэтому каждый стенд сторожа поднимался с `-ru`, и
#: английская полоса не сторожилась ничем.
LABELS = {
    "locale": Label("locale", "локаль"),
    "packages": Label("packages", "пакеты"),
    "ffmpeg": Label("ffmpeg", "ffmpeg"),
    "torrcast": Label("torrcast", "пакет torrcast"),
    "torrserver": Label("TorrServer", "TorrServer"),
    "sources": Label("sources", "источники"),
    "prowlarr": Label("Prowlarr", "Prowlarr"),
    "indexers": Label("indexers", "индексеры"),
    "config": Label("config", "конфиг"),
    "hls": Label("serving", "раздача"),
    "receiver": Label("receiver", "приёмник"),
    "facts": Label("warmup", "догрев"),
}
#: Работник фазы - там, где фаза подделывается часами (:func:`_fake`). Меряются
#: те из них, у кого в стенде есть отметки работы, остальные стенд не включал.
WORKERS = {
    "check_sources": "sources",
    "install_prowlarr": "prowlarr",
    "install_ffmpeg": "ffmpeg",
    "install_torrserver": "torrserver",
}

#: Стенд всех фаз разом. Список берётся у самого установщика: вписанная руками
#: копия разъехалась бы с источником молча, и «все двенадцать» тихо стали бы теми,
#: о которых помнил автор меры.
ALL_TWELVE = re.search(r"^UI_ALL_PHASES='(.*)'", SCRIPT, re.M).group(1)  # type: ignore[union-attr]

#: Перенос `phase_done` с `job_wait` на `job_start` - ровно та правка, против
#: которой поставлен сторож. Формула полосы, знаменатель и потолок 99 при этом
#: целы: ломается только связь «закрыто = сделано».
MOVED = {
    "install_ffmpeg": (
        (
            "    has ffmpeg     && job_start ffmpeg     install_ffmpeg\n",
            "    has ffmpeg     && { job_start ffmpeg install_ffmpeg; "
            "phase_done 'ffmpeg' 'ffmpeg'; }\n",
        ),
        (
            '        job_wait ffmpeg || die "ffmpeg was not installed - see the reason above" '
            '"ffmpeg не поставился - причина в строках выше"\n'
            "        phase_done 'ffmpeg' 'ffmpeg'\n",
            '        job_wait ffmpeg || die "ffmpeg was not installed - see the reason above" '
            '"ffmpeg не поставился - причина в строках выше"\n',
        ),
    ),
    "check_sources": (
        (
            "    has sources    && job_start sources    check_sources\n",
            "    has sources    && { job_start sources check_sources; "
            "phase_done 'sources' 'источники'; }\n",
        ),
        (
            "        job_wait sources || info "
            '"⚠ source check did not finish - see the lines above" '
            '"⚠ проверка источников не доработала - смотри строки выше"\n'
            "        phase_done 'sources' 'источники'\n",
            "        job_wait sources || info "
            '"⚠ source check did not finish - see the lines above" '
            '"⚠ проверка источников не доработала - смотри строки выше"\n',
        ),
    ),
}


class Close(NamedTuple):
    """Закрытие фазы в следе: момент, номер деления и ИМЯ фазы.

    Имя тут не украшение: пара «деление, имя» - то самое, что полоса печатает
    человеку в строке статуса, и то самое, чего не знала мера с жёсткой таблицей
    «фаза -> номер». Пара пишется рисовалкой на приход строки канала, а не по
    кадру: два закрытия внутри одного кадра оставили бы на экране только
    последнее, и мера ослепла бы на первое.
    """

    at: int
    mark: int
    phase: str


@dataclass(frozen=True)
class Run:
    """Прогон стенда: след полосы и часы работников, всё в мс эпохи."""

    frames: tuple[tuple[int, int], ...]  # (момент кадра, закрыто фаз)
    closings: tuple[Close, ...]
    total: int
    work: dict[str, tuple[int, int]]  # работник -> (начал, кончил)
    rc: int
    #: Язык, которым поднят стенд. Держится ЗДЕСЬ, а не в вызывающем: подпись фазы
    #: в следе - на языке прогона, и сверять её с чужим языком значит не опознать
    #: ни одной фазы (ровно это и происходило на `-en`).
    language: str
    screen_frames: tuple[str, ...]
    #: Весь поток pty целиком. Кадры заставки - только то, что ушло внутри DECSET
    #: 2026, а развал печатается ПОСЛЕ него: искать ложную строку в кадрах значило
    #: бы искать её там, где её не бывает даже на сломанном дереве.
    stream: str

    def took(self, mark: int) -> int | None:
        """Момент, когда полоса впервые показала `mark` закрытых фаз."""
        return next((t for t, done in self.frames if done >= mark), None)

    def held(self, mark: int) -> tuple[int, ...]:
        """Моменты кадров, на которых полоса показывала ровно `mark`."""
        return tuple(t for t, done in self.frames if done == mark)

    def closed(self, label: str) -> Close | None:
        """Закрытие этой фазы: номер деления и момент - ИЗ ПРОГОНА, не из таблицы."""
        return next((shut for shut in self.closings if shut.phase == label), None)

    def name(self, phase: str) -> str:
        """Подпись фазы на языке ЭТОГО прогона: пара в таблице, язык - в стенде."""
        return str(getattr(LABELS[phase], self.language))


def _fake(work: dict[str, float]) -> str:
    """Подделка работников. Проводку `main` не трогает: те же имена функций."""
    out = ["\n# --- TC-909: подделка долгих фаз (работники, не проводка) ---"]
    # Работник есть у каждой из двенадцати фаз, иначе стенд «всех фаз» упёрся бы в
    # настоящую установку: venv с pypi, опрос трекеров, обход сети за приёмником.
    for name in (
        "setup_locale",
        "install_packages",
        "install_torrcast",
        "check_sources",
        "install_prowlarr",
        "install_indexers",
        "setup_config",
        "setup_bot_unit",
        "setup_ha_unit",
        "setup_hls",
        "setup_receiver",
        "install_ffmpeg",
        "install_torrserver",
        "setup_facts",
        "setup_names",
    ):
        secs = work.get(name)
        if secs is None:
            out.append(f"{name}() {{ :; }}")
            continue
        out.append(
            f'{name}() {{ printf "%s\\n" "$EPOCHREALTIME" >"$TC909_MARK.{name}.begin"; '
            f'sleep {secs}; printf "%s\\n" "$EPOCHREALTIME" >"$TC909_MARK.{name}.done"; }}'
        )
    return "\n".join(out) + "\n\n"


def _rights(box: Path) -> dict[str, str]:
    """Стенд поднятия прав: обычный пользователь и шов, кончающийся `exec`.

    🔴 Настоящий sudo в этой проверке участвовать не может НИ НА КАКОМ шаге: найдя
    его, установщик поднялся бы по-настоящему и пошёл ставить продукт на машину,
    которая об этом не просила (куплено потерей, см. `_rights_stand` в
    test_install.py). Поэтому uid тут не меняется вовсе - подставка делает ровно то
    единственное, чем поднятие ломало заставку: заменяет процесс через `exec`.
    Канал прогресса это уносит при ЛЮБОМ sudo, даже всё сохраняющем: `UI_CHANNEL` -
    обычная переменная оболочки, она не экспортируется никуда и `exec` не переживает.
    Второго круга не будет: подставка метит окружение, а подставной `id` после метки
    отвечает «root» - иначе поднятие звало бы себя вечно.
    """
    bindir = box / "rights"
    bindir.mkdir()
    fake_id = bindir / "id"
    fake_id.write_text(
        '#!/bin/sh\n[ "$1" = -u ] || exec /usr/bin/id "$@"\n'
        '[ -n "${TC988_ELEVATED:-}" ] && { printf "0\\n"; exit 0; }\nprintf "1000\\n"\n',
        encoding="utf-8",
    )
    fake_id.chmod(0o755)
    sudo = box / "sudo"
    sudo.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{bindir / "sudo_calls.txt"}"\n'
        "while [ $# -gt 0 ]; do\n"
        "  case $1 in -H) shift ;; --) shift; break ;; *) break ;; esac\n"
        "done\n"
        'TC988_ELEVATED=1 exec "$@"\n',
        encoding="utf-8",
    )
    sudo.chmod(0o755)
    return {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TORRCAST_SUDO": str(sudo),
        # Ambient-переменная гейта выключила бы ровно то, что мерится; пустое
        # значение читается установщиком как «не задано».
        "TORRCAST_NO_ROOT": "",
    }


def _pty_run(
    script: Path, env: dict[str, str], args: tuple[str, ...] = (), limit: float = 120.0
) -> tuple[int, str]:
    """Прогон в настоящем pty: без tty install.sh рисовать не станет.

    ⚠️ Не `pty.fork`: гейт гоняет машинный набор в четыре процесса xdist, а тот
    многонитевой, и форк из-под нитей оставляет ребёнку захваченные ими замки -
    между `fork` и `exec` хватит одной аллокации, чтобы стадия встала намертво.
    `Popen` разводит эти два шага в C и не оставляет между ними питона вовсе.
    """
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    child = subprocess.Popen(
        ["bash", str(script), *args],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, **env},
        start_new_session=True,
    )
    os.close(slave)
    started = time.monotonic()
    stream = bytearray()
    while True:
        try:
            chunk = os.read(master, 65536)
            if not chunk:
                break
            stream.extend(chunk)
        except OSError:  # ребёнок ушёл и закрыл свой конец
            break
        if time.monotonic() - started > limit:
            child.kill()
            break
    os.close(master)
    return child.wait(), stream.decode("utf-8", errors="replace")


def _ms(path: Path) -> int:
    return int(float(path.read_text(encoding="utf-8").strip().replace(",", ".")) * 1000)


def _stand(
    text: str,
    box: Path,
    phases: str,
    work: dict[str, float],
    language: str = "en",
    rights: dict[str, str] | None = None,
) -> Run:
    """Поднять стенд на данном тексте install.sh и снять обе линии.

    `rights` - стенд поднятия прав (:func:`_rights`). Пусто - поднятие выключено
    через `TORRCAST_NO_ROOT`, как у всех мер про полосу, кроме одной.
    """
    assert ENTRY in text, "не найдена точка входа: подделку некуда вставить"
    script = box / "install.sh"
    script.write_text(text.replace(ENTRY, _fake(work) + ENTRY, 1), encoding="utf-8")
    # Перезапуск идёт по `$SELF`, то есть запуском самого файла, а не `bash файл`:
    # без бита исполнения поднятие упёрлось бы в отказ прав, а не в то, что мерится.
    script.chmod(0o755)
    for name in ("bin", "cfg", "state", "hls", "motd.d"):
        (box / name).mkdir()
    trace, mark = box / "ui.trace", box / "work"
    rc, stream = _pty_run(
        script,
        {
            "TERM": "xterm-256color",
            "LINES": str(ROWS),
            "COLUMNS": str(COLS),
            **({"TORRCAST_NO_ROOT": "1"} if rights is None else rights),
            "TORRCAST_NO_SYSTEMD": "1",
            "TORRCAST_PREFIX": str(box),
            "TORRCAST_BIN_DIR": str(box / "bin"),
            "TORRCAST_CONFIG_DIR": str(box / "cfg"),
            "TORRCAST_STATE_DIR": str(box / "state"),
            "TORRCAST_HLS_DIR": str(box / "hls"),
            "TORRCAST_INSTALL_LOG": str(box / "install.log"),
            "TORRCAST_MOTD": str(box / "motd"),
            "TORRCAST_MOTD_D": str(box / "motd.d"),
            "TORRCAST_PHASES": phases,
            "TORRCAST_UI_TRACE": str(trace),
            "TC909_MARK": str(mark),
        },
        ("-ru",) if language == "ru" else (),
    )
    written = trace.read_text(encoding="utf-8") if trace.exists() else ""
    seen = re.findall(r"(\d+) FRAME pct=\d+ done=(\d+) total=(\d+)", written)
    shut = re.findall(r"(\d+) CLOSE done=(\d+) total=\d+ phase=(.*)", written)
    done: dict[str, tuple[int, int]] = {}
    for name in work:
        begin_at, done_at = box / f"work.{name}.begin", box / f"work.{name}.done"
        assert begin_at.exists() and done_at.exists(), f"{name} не отметил свою работу"
        done[name] = (_ms(begin_at), _ms(done_at))
    screen_frames = tuple(
        match.group(1)
        for match in re.finditer(
            re.escape(SYNC_ON) + "(.*?)" + re.escape(SYNC_OFF), stream, re.DOTALL
        )
    )
    return Run(
        tuple((int(t), int(d)) for t, d, _ in seen),
        tuple(Close(int(t), int(mark), phase) for t, mark, phase in shut),
        int(seen[0][2]) if seen else 0,
        done,
        rc,
        language,
        screen_frames,
        stream,
    )


def _shape(run: Run, total: int) -> None:
    """Стенд поднялся и прибор имел шанс выстрелить."""
    assert run.rc == 0, f"стенд не дошёл до конца: rc={run.rc}"
    assert run.total == total, f"фаз всего {run.total}, ждали {total}"
    assert len(run.frames) >= 40, f"кадров {len(run.frames)}: мерить не на чем"
    assert run.frames[-1][1] == total, f"полоса не досчитала: {run.frames[-1]}"


def _language_coverage(run: Run, language: str) -> tuple[int, int, int, list[str]]:
    """Охват кадрового языкового прибора и найденные кириллические слова."""
    frames = run.screen_frames
    visible = tuple(LANG_DOOR.sub("", ANSI.sub("", frame)) for frame in frames)
    nonempty = sum(bool(frame.strip()) for frame in visible)
    phases = sum(bool(re.search(r"(?:phase|фаза) \d+/\d+:", frame)) for frame in visible)
    characters = sum(len(frame) for frame in visible)
    found = [
        f"кадр {number}: {', '.join(dict.fromkeys(CYRILLIC.findall(frame)))}"
        for number, frame in enumerate(visible, 1)
        if CYRILLIC.search(frame)
    ]
    coverage = (
        f"язык {language}: кадров {len(frames)}, непустых {nonempty}, "
        f"фаз замечено {phases}, символов просмотрено {characters}"
    )
    assert frames, f"прибор ничего не увидел: {coverage}"
    assert nonempty, f"прибор снял только пустые кадры: {coverage}"
    assert phases, f"прибор не увидел ни одной фазы: {coverage}"
    assert characters, f"прибор не просмотрел ни одного символа: {coverage}"
    return nonempty, phases, characters, found


def _moved(where: str) -> str:
    text = SCRIPT
    for old, new in MOVED[where]:
        assert old in text, f"перенос не на что наложить:\n{old}"
        text = text.replace(old, new, 1)
    return text


def _plateau(run: Run) -> tuple[int, int]:
    """Плато на делении перед долгой фазой: (кадров, охват в мс)."""
    stay = run.held(BEFORE)
    return len(stay), (stay[-1] - stay[0]) if len(stay) > 1 else 0


def _slack(work: int) -> int:
    """Допуск запаздывания для доклада о работе длиной `work` мс.

    Два слагаемых, оба выведенные, ни одного подобранного: пол - квантование
    самого прибора (:data:`LAG_FRAMES` кадров следа, тот же, что у ранней
    стороны), а доля работы поднимает допуск там, где работа длинная и кадров в
    ней много. Замер 05-09-2026 на честном прогоне всех фоновых фаз: деления
    брались на 4, 16, 52 и 52 мс РАНЬШЕ момента готовности, то есть запаздывания
    в честном дереве нет вовсе, а пол допуска - 366 мс. Отрицательная проба на
    том же стенде даёт +1449 мс. Разрыв четырёхкратный, и подгонять тут нечего.
    """
    return max(LAG_FRAMES * FRAME_MS, work // 4)


def _out_of_step(run: Run) -> list[str]:
    """Жалобы на фазы, чьё деление разошлось с их собственной работой.

    🔴 Мерятся ОБЕ стороны. Ранняя проста: доложить о фазе раньше, чем кончилась
    её работа, нельзя никогда. Поздняя сложнее, и «не позже конца своей работы»
    тут было бы ложной краснотой: задания идут параллельно, а `main` закрывает
    фазы по очереди, поэтому фаза, отработавшая раньше очереди, честно ждёт её
    (TorrServer в честном прогоне ждёт ffmpeg целую секунду). Поздняя сторона
    поэтому меряется от момента, раньше которого доложить было НЕЧЕГО: самой
    поздней из работ, стоящих в очереди до этой фазы включительно.

    Порядок очереди берётся из прогона - из порядка, в котором полоса называла
    имена, - а не из таблицы: таблица уводила замер на чужую фазу молча.
    """
    labels = {run.name(phase): worker for worker, phase in WORKERS.items() if worker in run.work}
    complaints: list[str] = []
    ready, seen = 0, set()
    for shut in run.closings:
        worker = labels.get(shut.phase)
        if worker is None or worker in seen:
            continue
        seen.add(worker)
        began, ended = run.work[worker]
        work, slack = ended - began, _slack(ended - began)
        ready = max(ready, ended)
        place = f"{shut.phase}: деление {shut.mark}/{run.total} при работе {work} мс"
        if shut.at < ended - LAG_FRAMES * FRAME_MS:
            complaints.append(
                f"{place} взято на {ended - shut.at} мс РАНЬШЕ конца своей работы "
                f"(допуск {LAG_FRAMES * FRAME_MS} мс)"
            )
        elif shut.at > ready + slack:
            complaints.append(
                f"{place} взято на {shut.at - ready} мс ПОЗЖЕ того, как доклад стал "
                f"возможен (допуск {slack} мс)"
            )
    complaints += [
        f"{run.name(phase)}: полоса не закрыла эту фазу ни одним делением"
        for worker, phase in WORKERS.items()
        if worker in run.work and worker not in seen
    ]
    return complaints


def _main_body(text: str) -> str:
    found = re.search(r"\nmain\(\) \{\n(.*?)\n\}\n", text, re.S)
    assert found is not None, "тело main не найдено: якорю не с чем сверяться"
    return found.group(1)


def _mislabelled(text: str) -> list[str]:
    """🔴 Якорь: подпись фазы обязана стоять в блоке ЕЁ фазы.

    Номер деления мера больше не держит таблицей, но связь «подпись <-> работа»
    держать нечем, кроме текста `main`: полоса печатает подпись, а какая работа
    за ней стоит, знает только тот, кто эту подпись рядом с работой поставил.
    Перестановка двух вызовов `phase_done` не двигает ни одной секунды и для
    временнЫх сверок невидима - здесь она и краснеет.

    Блок фазы открывает `has <фаза>`: `job_wait` соседа внутри блока подписи не
    крадёт, а именно им ломается своевременность доклада.

    🔴 TC-1052. Сверяются ОБЕ подписи разом. Одноязычный якорь держал бы английскую
    половину пары ровно так же, как её держал литерал `installation`, - никак.
    """
    complaints: list[str] = []
    named = set()
    phase = ""
    for token in re.finditer(r"\bhas (\w+)\b|phase_done '([^']*)' '([^']*)'", _main_body(text)):
        opened, pair = token.group(1), (token.group(2), token.group(3))
        if opened is not None:
            phase = opened
            continue
        if pair != LABELS.get(phase):
            complaints.append(
                f"фаза {phase} закрывается подписью {pair!r}, а её подпись - "
                f"{LABELS.get(phase, 'фазы нет вовсе')!r}"
            )
        named.add(phase)
    complaints += [
        f"фаза {phase} не закрывается ничем: подпись {label!r} не встретилась в main"
        for phase, label in LABELS.items()
        if phase not in named
    ]
    return complaints


#: Запаздывание: доклад о фазе уезжает за `job_wait` СОСЕДА, то есть на секунды
#: после конца её собственной работы. Подпись при этом остаётся в своём блоке
#: (якорю не за что зацепиться), порядок `job_start`/`job_wait` цел, результат на
#: месте - двигается ровно момент доклада.
LATE = {
    "install_ffmpeg": (
        "        phase_done 'ffmpeg' 'ffmpeg'\n",
        '        job_wait torrserver || die "TorrServer was not installed - see the reason above" '
        '"TorrServer не поставился - причина в строках выше"\n'
        "        phase_done 'ffmpeg' 'ffmpeg'\n",
    ),
}


def _late(where: str) -> str:
    old, new = LATE[where]
    assert SCRIPT.count(old) == 1, f"запаздывание не на что наложить:\n{old}"
    return SCRIPT.replace(old, new, 1)


#: 🔴 TC-988. Возврат поднятия внутрь работника - ровно та правка, против которой
#: поставлен сторож ниже. Больше не меняется ничего: полоса, знаменатель и посадка
#: целы, ломается только то, что `exec` уносит форкнутого работника вместе с каналом.
INSIDE_WORKER = (
    (
        "main() {\n    cleanup_login_notice\n",
        "main() {\n    become_root\n    cleanup_login_notice\n",
    ),
    (
        "else\n    become_root\n    if [[ -t 1 && -z ${TORRCAST_PLAIN:-} ]]; then\n"
        '        ui_run real\n    else\n        main "$@"\n    fi\nfi\n',
        "elif [[ -t 1 && -z ${TORRCAST_PLAIN:-} ]]; then\n    ui_run real\nelse\n"
        '    main "$@"\nfi\n',
    ),
)


def _elevation_inside_worker() -> str:
    text = SCRIPT
    for old, new in INSIDE_WORKER:
        assert old in text, f"возврат не на что наложить:\n{old}"
        text = text.replace(old, new, 1)
    return text


@pytest.mark.machine
def test_english_frames_have_no_cyrillic_and_russian_frames_do(tmp_path: Path) -> None:
    """Язык меряется по кадрам PTY, включая финальную заставку, в обе стороны."""
    for language in ("en", "ru"):
        box = tmp_path / language
        box.mkdir()
        run = _stand(SCRIPT, box, ALL_PHASES, ALL_WORK, language)
        _shape(run, ALL_TOTAL)
        nonempty, phases, characters, found = _language_coverage(run, language)
        coverage = (
            f"язык {language}: кадров {len(run.screen_frames)}, непустых {nonempty}, "
            f"фаз замечено {phases}, символов просмотрено {characters}"
        )
        final = ANSI.sub("", run.screen_frames[-1])
        if language == "en":
            assert "find and play on TV" in final, f"финальный английский кадр не снят: {coverage}"
            assert LANG_DOOR.search(final), f"дверь в русский пропала из кадра: {coverage}"
            assert not found, f"кириллица в английских кадрах ({coverage}): {'; '.join(found)}"
        else:
            assert "найти и включить на ТВ" in final, f"финальный русский кадр не снят: {coverage}"
            assert "cast --en" in final and "English" in final, (
                f"дверь в английский пропала из кадра: {coverage}"
            )
            assert found, f"русские кадры не содержат кириллицы: {coverage}"
        print(f"{coverage}, кириллических кадров {len(found)}")


@pytest.mark.machine
@pytest.mark.parametrize(
    ("language", "hidden", "final"),
    (
        ("en", "ordinary degradation", "passwordless sudo was granted"),
        ("ru", "обычное ухудшение", "беспарольный sudo выдан"),
    ),
)
def test_warnings_stay_in_the_log_but_sudo_notices_follow_success(
    tmp_path: Path, language: str, hidden: str, final: str
) -> None:
    """The warning panel is gone; only a rights notice survives after [OK]."""
    injected = SCRIPT.replace(
        "main() {\n    cleanup_login_notice\n",
        "main() {\n"
        "    loud 'ordinary degradation' 'обычное ухудшение'\n"
        "    final_loud 'passwordless sudo was granted' 'беспарольный sudo выдан'\n"
        "    cleanup_login_notice\n",
        1,
    )
    run = _stand(injected, tmp_path, HOLD_PHASES, HOLD_WORK, language)
    _shape(run, HOLD_TOTAL)
    visible = ANSI.sub("", run.stream)
    journal = (tmp_path / "install.log").read_text(encoding="utf-8")

    assert hidden in journal and final in journal
    assert hidden not in visible
    assert "и ещё" not in visible
    assert visible.index("[OK]") < visible.index(final)


@pytest.mark.machine
def test_failure_shows_only_the_tail_and_the_journal_path(tmp_path: Path) -> None:
    """A long worker log is kept on disk; one screenful reaches the terminal."""
    needle = '    if [ -n "$CATALOG_CUT_EN" ]; then\n'
    injected = SCRIPT.replace(
        needle,
        "    for i in {1..120}; do printf 'long journal line %03d\\n' \"$i\"; done\n"
        "    die 'measured failure' 'измеренный отказ'\n" + needle,
        1,
    )
    run = _stand(injected, tmp_path, HOLD_PHASES, HOLD_WORK)
    visible = ANSI.sub("", run.stream)
    journal_path = tmp_path / "install.log"
    journal = journal_path.read_text(encoding="utf-8")

    assert run.rc != 0
    assert len(journal.splitlines()) >= 120
    assert "long journal line 101" not in visible
    assert "long journal line 102" in visible
    assert "long journal line 120" in visible
    assert "measured failure" in visible
    assert f"installation log: {journal_path}" in visible


@pytest.mark.machine
def test_the_bar_holds_its_mark_for_as_long_as_the_phase_is_still_working(
    tmp_path: Path,
) -> None:
    """🔴 Плато у самой долгой фазы длиной ровно в её работу - в кадрах и секундах.

    Порог выведен из длительности работы, а не подобран под прогон: короче -
    сторож слепнет к полосе, обгоняющей работу, длиннее - к полосе, замершей на
    делении и прыгающей потом через два. Полоса, идущая от запусков, плато не
    даёт вовсе: она проскакивает деление сразу.
    """
    run = _stand(SCRIPT, tmp_path, HOLD_PHASES, HOLD_WORK, "ru")
    _shape(run, HOLD_TOTAL)
    began, ended = run.work["install_ffmpeg"]
    work = ended - began
    assert work >= SLOW_S * 900, f"подделка не проработала своё: {work} мс"

    inside = tuple(d for t, d in run.frames if began <= t <= ended - LAG_FRAMES * FRAME_MS)
    frames, span = _plateau(run)
    seen = (
        f"плато {frames} кадров ({span / 1000:.2f} с) при работе {work / 1000:.2f} с, "
        f"кадров внутри работы {len(inside)}"
    )
    # 🔴 Ноль пуст, пока прибор не имел шанса выстрелить: окно без единого кадра
    # дало бы зелень на пустом множестве, а не доказательство плато.
    assert len(inside) >= (work / FRAME_MS) * 0.6, f"окно работы пусто: {seen}"
    assert set(inside) == {BEFORE}, f"полоса ушла с деления, пока работа шла: {seen}"
    assert span >= work - 2 * FRAME_MS, f"плато короче работы: {seen}"
    assert span <= work + _slack(work), f"полоса замерла на делении дольше работы: {seen}"
    print(seen)

    took = run.took(BEFORE + 1)
    assert took is not None and took >= ended - LAG_FRAMES * FRAME_MS, (
        f"деление взято на {ended - (took or 0)} мс раньше конца работы: {seen}"
    )


@pytest.mark.machine
def test_every_background_phase_closes_in_step_with_its_own_work(tmp_path: Path) -> None:
    """Ни одна фоновая фаза не закрывается ни раньше своей работы, ни позже очереди.

    Задания идут параллельно, поэтому четыре разной длины стоят одной самой
    долгой. Сверка идёт по каждой и с обеих сторон: сторож, следящий за одной
    фазой и за одним только опережением, пропустил бы и перенос у соседней, и
    замершую полосу.
    """
    run = _stand(SCRIPT, tmp_path, ALL_PHASES, ALL_WORK, "ru")
    _shape(run, ALL_TOTAL)

    ready, drift = 0, []
    for worker, phase in WORKERS.items():
        shut = run.closed(run.name(phase))
        ready = max(ready, run.work[worker][1])
        seen = f"{shut.mark}/{run.total} на {shut.at - ready} мс" if shut else "не взято"
        drift.append(f"{run.name(phase)} {seen}")
    print("деление от момента, когда доклад стал возможен: " + "; ".join(drift))
    assert not (out := _out_of_step(run)), "деление разошлось с работой - " + "; ".join(out)


@pytest.mark.machine
def test_a_phase_closing_behind_a_neighbour_wait_is_caught(tmp_path: Path) -> None:
    """🔴 Отрицательная проба на ЗАПАЗДЫВАНИИ: доклад уехал за `job_wait` соседа.

    Ровно тот вход, на котором прежний односторонний сторож был зелёным: полоса
    ничего не обгоняет, результат на месте, установка возвращает ноль - деление
    просто берётся секундами позже, чем работа кончилась. Человеку это видно как
    замершая полоса и прыжок через два деления. Подпись фазы при этом остаётся в
    своём блоке, поэтому якорь :func:`_mislabelled` тут молчит: краснеет именно
    время, и краснеет оно ДРУГИМ узлом, чем перестановка.
    """
    run = _stand(_late("install_ffmpeg"), tmp_path, HOLD_PHASES, LATE_WORK, "ru")
    _shape(run, HOLD_TOTAL)
    assert run.rc == 0, "запаздывание обязано оставаться незаметным снаружи"
    assert not _mislabelled(_late("install_ffmpeg")), "якорь сработал не на своём входе"

    work = run.work["install_ffmpeg"][1] - run.work["install_ffmpeg"][0]
    frames, span = _plateau(run)
    assert span > work + _slack(work), f"полоса не замерла: плато {frames} кадров, {span} мс"
    out = _out_of_step(run)
    assert any("ffmpeg" in line and "ПОЗЖЕ" in line for line in out), (
        f"запаздывание не поймано: {out or 'жалоб нет вовсе'}"
    )
    print(f"плато {frames} кадров ({span} мс) при работе {work} мс; поймано: {'; '.join(out)}")


def test_each_phase_is_closed_by_its_own_label_in_main() -> None:
    """🔴 Якорь: подпись каждой фазы стоит в блоке своей фазы, и фаз столько же.

    Меру времени эта сверка не дублирует: перестановка двух `phase_done` не
    двигает ни одной секунды. Без якоря полоса называла бы человеку одну фазу,
    закрывая работу другой, а замер этого не видел бы вовсе.
    """
    known = re.search(r"^UI_ALL_PHASES='([^']*)'", SCRIPT, re.M)
    assert known is not None, "список фаз в install.sh не найден"
    assert set(known.group(1).split()) == set(LABELS), (
        f"фазы установщика и подписи разошлись: {sorted(set(known.group(1).split()) ^ set(LABELS))}"
    )
    assert not (bad := _mislabelled(SCRIPT)), "подпись не на своей фазе - " + "; ".join(bad)


@pytest.mark.machine
@pytest.mark.parametrize("language", ("en", "ru"))
def test_all_twelve_phases_name_themselves_in_the_language_of_the_run(
    tmp_path: Path, language: str
) -> None:
    """🔴 TC-1052. Каждое из двенадцати делений называет СВОЮ фазу на языке прогона.

    Стенд поднимается ключом языка и больше ничем: подписи мера берёт из той же
    таблицы, что и временные сверки, а номера делений - из самого прогона. На `-en`
    в канал уходил один литерал `installation` на все двенадцать закрытий, поэтому
    опознать по паре «деление, имя» не удавалось ни одной фазы (0 из 12), и каждый
    временной стенд поднимался с `-ru` - английская полоса не сторожилась ничем.

    Узлов тут два, по одному на язык, и краснеют они порознь: пропажа имени на одном
    языке оставляет второй зелёным, а вместе они не дают ни одной ветке остаться
    голой. Времени эта мера не мерит вовсе - его держат соседние узлы.
    """
    run = _stand(SCRIPT, tmp_path, ALL_TWELVE, HOLD_WORK, language)
    assert run.rc == 0, f"стенд не дошёл до конца: rc={run.rc}"
    assert run.total == len(LABELS), f"фаз всего {run.total}, ждали {len(LABELS)}"
    assert run.frames and run.frames[-1][1] == run.total, f"полоса не досчитала: {run.frames[-1:]}"

    marks = {shut.phase: shut.mark for shut in run.closings}
    want = {run.name(phase) for phase in LABELS}
    seen = (
        f"язык {language}: опознано {len(want & set(marks))} из {len(LABELS)}, "
        f"закрытий в следе {len(run.closings)}"
    )
    assert set(marks) >= want, f"{seen}; не опознаны: {sorted(want - set(marks))}"
    assert sorted(marks.values()) == list(range(1, len(LABELS) + 1)), (
        f"{seen}; деления разъехались: {sorted(marks.items(), key=lambda pair: pair[1])}"
    )

    # Тот же ответ, но глазами человека: пара едет в строку статуса, а не только в
    # след. Спрашивается фаза, на которой полоса СТОИТ (следом за ней `main` ждёт
    # ffmpeg): мгновенная фаза может уместиться между двумя кадрами вся целиком.
    word = "фаза" if language == "ru" else "phase"
    visible = ANSI.sub("", run.stream)
    held = f"{word} {marks[run.name('receiver')]}/{run.total}: {run.name('receiver')}"
    assert held in visible, f"{seen}; строки статуса {held!r} на экране нет"
    assert not re.search(rf"{word} \d+/\d+: installation", visible), (
        f"{seen}; фаза названа человеку литералом installation"
    )
    print(f"{seen}; на экране {held!r}")


def test_two_swapped_labels_are_caught_by_the_anchor() -> None:
    """🔴 Отрицательная проба на ПЕРЕСТАНОВКЕ: две подписи поменялись местами.

    Взяты мгновенные фазы: работы у них нет вовсе, поэтому ни один замер времени
    такую перестановку увидеть не может в принципе. Ловит её только якорь, и
    называет обе фазы вслух.
    """
    swapped = SCRIPT.replace("phase_done 'serving' 'раздача'", "phase_done '~' '~'", 1)
    swapped = swapped.replace(
        "phase_done 'receiver' 'приёмник'", "phase_done 'serving' 'раздача'", 1
    )
    swapped = swapped.replace("phase_done '~' '~'", "phase_done 'receiver' 'приёмник'", 1)
    assert swapped != SCRIPT, "перестановка не наложилась: пробе нечего ломать"

    # Жалоба разбирается по фазам, а не грепом по всему тексту: обе подписи стоят в
    # одной строке жалобы, и грепом «receiver и раздача» одна и та же строка закрыла
    # бы обе проверки - вторая фаза осталась бы неспрошенной.
    bad = _mislabelled(swapped)
    caught = {line.split()[1]: line.split(", а её подпись")[0] for line in bad}
    assert "приёмник" in caught.get("hls", ""), f"якорь молчит про hls: {bad}"
    assert "раздача" in caught.get("receiver", ""), f"якорь молчит про receiver: {bad}"


@pytest.mark.machine
def test_phase_done_moved_to_job_start_kills_the_plateau(tmp_path: Path) -> None:
    """🔴 Сторож обязан уметь стрелять: та же мера на подделке БЕЗ плато.

    Ломается ровно то, против чего сторож поставлен, - момент вызова
    `phase_done` у ffmpeg. Формула полосы, знаменатель и потолок 99 целы,
    поэтому все меры TC-885 такую установку пропускают зелёной, а сама она
    возвращает ноль. Красным её делает только окно работы.
    """
    run = _stand(_moved("install_ffmpeg"), tmp_path, HOLD_PHASES, HOLD_WORK, "ru")
    _shape(run, HOLD_TOTAL)
    began, ended = run.work["install_ffmpeg"]

    frames, span = _plateau(run)
    assert run.rc == 0, "перенос обязан оставаться незаметным снаружи"
    assert span < (ended - began) / 2, f"плато уцелело: {frames} кадров, {span} мс"
    out = _out_of_step(run)
    assert any("ffmpeg" in line and "РАНЬШЕ" in line for line in out), (
        f"опережение не поймано: {out or 'жалоб нет вовсе'}"
    )


@pytest.mark.machine
def test_the_same_move_on_another_phase_is_caught_too(tmp_path: Path) -> None:
    """🔴 И то же самое у СОСЕДНЕЙ фазы: перенос у `источников` виден так же."""
    run = _stand(_moved("check_sources"), tmp_path, ALL_PHASES, ALL_WORK, "ru")
    _shape(run, ALL_TOTAL)

    out = _out_of_step(run)
    assert any("источники" in line and "РАНЬШЕ" in line for line in out), (
        f"опережение не поймано: {out or 'жалоб нет вовсе'}"
    )


#: Ложная строка развала: её печатает `ui_collapse`, когда работник кончился, а
#: фазы не добраны. Ищется по обоим языкам - заставка говорит на языке человека.
BROKE_OFF = ("installation broke off", "установка оборвалась")


def _rights_run(text: str, box: Path) -> tuple[Run, str, Path]:
    """Прогон под заставкой ОБЫЧНЫМ пользователем: поднятие идёт по-настоящему."""
    rights = _rights(box)
    run = _stand(text, box, HOLD_PHASES, HOLD_WORK, rights=rights)
    return run, run.stream, box / "rights" / "sudo_calls.txt"


@pytest.mark.machine
def test_the_bar_walks_when_a_plain_user_is_the_one_who_started_it(tmp_path: Path) -> None:
    """🔴 TC-988. Полоса идёт и у того, кто позвал установщик БЕЗ sudo.

    Мерился всегда `sudo ./install.sh`, то есть вход, на котором поднятие
    возвращается сразу и `exec` не случается вовсе. Человек и однострок ходят
    другим входом, и на нём заставка мерила пустой канал: полоса стояла на 0 %
    всю установку, а в конце врала «оборвалась» на прошедшей установке.
    """
    run, stream, calls = _rights_run(SCRIPT, tmp_path)

    assert calls.exists(), "поднятие не звалось вовсе: мера ничего не проверила"
    _shape(run, HOLD_TOTAL)
    # Нуля среди делений может и не быть: поднятие с перезапуском стоит времени, и
    # первая (мгновенная) фаза успевает закрыться до первого же кадра. Мерка тут -
    # что полоса ИДЁТ и доходит до конца, а не с какого деления её застали.
    marks = sorted({done for _, done in run.frames})
    assert marks[-1] == HOLD_TOTAL, f"полоса не дошла до конца шкалы: {marks}"
    assert len(marks) >= 3, f"полоса показала меньше трёх делений: {marks}"
    assert run.rc == 0, f"установка не дошла до конца: rc={run.rc}"
    for lie in BROKE_OFF:
        assert lie not in stream, f"прошедшая установка названа оборванной: {lie!r}"


@pytest.mark.machine
def test_elevation_moved_back_into_the_worker_freezes_the_bar_at_zero(tmp_path: Path) -> None:
    """🔴 Отрицательная проба: поднятие возвращено в `main` - полоса встаёт на нуле.

    Ровно тот отказ, который владелец предъявил дословно: ни одного деления за
    всю установку, ложная строка развала и НОЛЬ кодом возврата под ней.
    """
    run, stream, calls = _rights_run(_elevation_inside_worker(), tmp_path)

    assert calls.exists(), "поднятие не звалось вовсе: мера ничего не проверила"
    assert len(run.frames) >= 20, f"кадров {len(run.frames)}: мерить не на чем"
    assert {done for _, done in run.frames} == {0}, "полоса всё же сдвинулась"
    assert any(lie in stream for lie in BROKE_OFF), "ложная строка развала не найдена"
    assert run.rc == 0, f"ноль кодом возврата под ложью не воспроизведён: rc={run.rc}"
