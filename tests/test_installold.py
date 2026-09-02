"""🔴 TC-980. Заставка установщика обязана дорисоваться на bash 3.2.

Штатный интерпретатор мака - `GNU bash, version 3.2.57`, и под `set -u` первое же
обращение к `EPOCHREALTIME` (bash 5.0) убивало заставку на первой строке: человек за
маком получал `install.sh: line NNNN: EPOCHREALTIME: unbound variable` вместо
установки. Попаданий было шесть, все внутри рисовалки, и все шесть - разные
возможности разных версий bash.

Сторожа тут два, и охваты у них РАЗНЫЕ - в этом и смысл двух.

* Текстовый ловит КЛАСС, а не эти шесть строк: он знает список конструкций bash 4+/5+
  и требует, чтобы каждая встреченная жила внутри развилки по версии интерпретатора.
  Седьмую, которую сегодня никто не написал, он поймает так же, как первую. Список
  строк-нарушителей в нём не хранится вовсе, иначе правило закрывалось бы снимком.
* Живой прогоняет рисовалку под НАСТОЯЩИМ старым bash. Гейт стоит на Linux, где
  bash 5.3, и текстом «оно работает» не доказать - это разбор, а не замер. Старый bash
  на машине гейта не растёт сам: путь к нему называют переменной `TORRCAST_BASH32`
  (собирается из исходников 3.2.57). Без него замера НЕТ, и тест это говорит вслух
  через skip, а не зеленеет: зелень на пустом множестве тут была бы ровно тем прибором,
  который отвечает «годен» там, где мерить не может.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import shutil
import struct
import subprocess
import termios
import time
from pathlib import Path

import pyte
import pytest

REPO = Path(__file__).parents[1]
SCRIPT_PATH = REPO / "install.sh"
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")

ROWS, COLS = 30, 100
SYNC_ON, SYNC_OFF = "\x1b[?2026h", "\x1b[?2026l"
#: Длина холостой подачи, секунд. Короче - и посадка съедает почти всю дугу, мерить
#: становится нечего; длиннее - гейт платит секундами ни за что.
DRY_SECONDS = 5

#: Конструкции, которых у bash 3.2 нет. Ключ - имя класса с версией, где он появился;
#: значение - образец, а не адрес. Ни одной строки install.sh тут не названо.
MODERN: dict[str, str] = {
    "EPOCHREALTIME/EPOCHSECONDS (5.0)": r"\bEPOCH(?:REALTIME|SECONDS)\b",
    "SRANDOM (5.1)": r"\bSRANDOM\b",
    "дескриптор с автономером {fd} (4.1)": r"(?<![$\w])\{[A-Za-z_]\w*\}\s*[<>]",
    "нецелый таймаут read -t (4.0)": r"\bread\b[^\n;|&]*?\s-t\s+(?!\d+(?:\s|$))\S+",
    "ассоциативный массив -A (4.0)": r"\b(?:declare|local|typeset)\s+(?:-\w+\s+)*-\w*A\b",
    "ссылка на имя -n (4.3)": r"\b(?:declare|local|typeset)\s+(?:-\w+\s+)*-\w*n\b",
    "глобальное объявление -g (4.2)": r"\b(?:declare|typeset)\s+(?:-\w+\s+)*-\w*g\b",
    "mapfile/readarray (4.0)": r"\b(?:mapfile|readarray)\b",
    "coproc (4.0)": r"(?<![\w-])coproc\b",
    "wait -n (4.3)": r"\bwait\s+-\w*n\b",
    "смена регистра ${v^^} и ${v,,} (4.0)": r"\$\{[#!]?\w+(?:\[[^\]]*\])?(?:\^{1,2}|,{1,2})[^}]*\}",
    "преобразование ${v@Q} (4.4)": r"\$\{[^{}]*@[QEPAaKkUuLc]\}",
    "printf со временем %(fmt)T (4.2)": r"%\([^)]*\)T",
    "printf -v по элементу массива (4.1)": r"\bprintf\s+-v\s+\w+\[",
    "shopt globstar/lastpipe (4.0/4.2)": r"\bshopt\s+-[su]\s+(?:globstar|lastpipe)\b",
    "проверка -v (4.2)": r"\[\[?\s+-v\s",
    "провал рукава case ;& и ;;& (4.0)": r";;&|;&(?:\s|$)",
    "перенаправления &>> и |& (4.0)": r"&>>|\|&",
    "отрицательный индекс массива (4.2)": r"\$\{\w+\[-",
}

#: Чем в install.sh называется развилка по версии интерпретатора. Сторож смотрит на
#: ФОРМУ развилки, а не на номер версии: `if (( UI_HAS_EPOCH ))` и `if ((
#: BASH_VERSINFO[0] >= 5 ))` для него одно и то же.
VERSION_FORK = re.compile(r"UI_HAS_[A-Z_]+|BASH_VERSINFO")
#: `if`/`fi` считаются только в позиции ключевого слова: `0 if parts(...) else 1` внутри
#: вставленного питона - не оболочечное ветвление, а тела heredoc сторож и вовсе не
#: видит (см. :func:`_strip`).
IF_TOKEN = re.compile(r"(?:^|[;&|(){}]|\bthen\b|\belse\b|\bdo\b)\s*(if|elif|fi)(?![\w./-])")
HEREDOC = re.compile(r"<<-?\s*(?:'([A-Za-z_]\w*)'|\"([A-Za-z_]\w*)\"|\\?([A-Za-z_]\w*))")


def _strip(text: str, blank_quotes: bool) -> str:
    """Текст без комментариев (и, по просьбе, без содержимого кавычек). Строки целы.

    Кавычки считаются по ВСЕМУ файлу, а не построчно: одиночные кавычки в install.sh
    переживают перевод строки (многострочные фильтры jq), и построчный разбор ловил бы
    их `if ... then ... else ... end` как оболочечные. Он же не спутает `#` внутри
    строки с началом комментария.

    Вложенность if/fi считается по тексту БЕЗ кавычек, а сами конструкции ищутся в
    тексте С кавычками: `read -t "$s"` без них выглядит как `read -t`, то есть прибор
    сам стирал бы то, что пришёл измерять.
    """

    def hide(chunk: str) -> str:
        """Убрать смысл, сохранив длину и все переводы строк: нумерация строк - мера."""
        return "".join("\n" if ch == "\n" else " " for ch in chunk)

    def body_end(start: int, delimiter: str) -> int:
        """Конец тела heredoc: строка-терминатор либо конец файла."""
        at = start
        while at < n:
            stop = text.find("\n", at)
            stop = n if stop < 0 else stop
            if text[at:stop].strip() == delimiter:
                return at
            at = stop + 1
        return n

    out: list[str] = []
    quote: str | None = None
    pending: list[str] = []
    prev = "\n"
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        pair = text[i : i + 2]
        if ch == "\n" and pending and not quote:
            out.append("\n")
            i += 1
            for delimiter in pending:
                stop = body_end(i, delimiter)
                out.append(hide(text[i:stop]))
                i = stop
            pending.clear()
            prev = "\n"
            continue
        if not quote and pair == "<<" and text[i + 2 : i + 3] != "<":
            here = HEREDOC.match(text, i)
            if here:
                pending.append(here.group(1) or here.group(2) or here.group(3))
                out.append(hide(here.group(0)))
                prev = " "
                i = here.end()
                continue
        if quote:
            step = 2 if (ch == "\\" and quote == '"' and i + 1 < n) else 1
            chunk = text[i : i + step]
            out.append(hide(chunk) if blank_quotes else chunk)
            if step == 1 and ch == quote:
                quote = None
            i += step
            continue
        if ch == "\\" and i + 1 < n:
            out.append(hide(pair) if blank_quotes else pair)
            i += 2
            continue
        if ch in "'\"":
            quote = ch
            out.append(" " if blank_quotes else ch)
            prev = " "
            i += 1
            continue
        if ch == "#" and prev in " \t\n;&|(":
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(" " * (end - i))
            i = end
            continue
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out)


def _fork_cover(text: str) -> tuple[dict[int, bool], int]:
    """Для каждой строки: стоит ли она внутри развилки по версии. Второе - остаток глубины.

    Развилка накрывает ОБЕ свои ветки: запасной путь для старого bash - такая же её
    часть, как быстрый путь для нового.
    """
    code = _strip(text, blank_quotes=True)
    stack: list[bool] = []
    cover: dict[int, bool] = {}
    for number, line in enumerate(code.splitlines(), 1):
        forked = bool(VERSION_FORK.search(line))
        opened = False
        for token in IF_TOKEN.findall(line):
            if token == "if":
                stack.append(forked)
                opened = True
            elif token == "elif" and stack:
                stack[-1] = stack[-1] or forked
            elif token == "fi" and stack:
                stack.pop()
        cover[number] = any(stack) or (opened and forked)
    return cover, len(stack)


def _offenders(text: str) -> list[str]:
    """Конструкции bash 4+/5+ вне развилки по версии, по одной строке на находку."""
    cover, leftover = _fork_cover(text)
    assert leftover == 0, (
        f"сторож не разобрал вложенность if/fi (остаток {leftover}): мерить он не может, "
        "и молчать об этом права не имеет"
    )
    code = _strip(text, blank_quotes=False).splitlines()
    found: list[str] = []
    for number, line in enumerate(code, 1):
        for name, pattern in MODERN.items():
            for hit in re.finditer(pattern, line):
                if not cover[number]:
                    found.append(f"строка {number}: {name}: {hit.group(0).strip()!r}")
    return found


def test_modern_bash_constructs_in_the_installer_live_only_inside_a_version_fork() -> None:
    """Каждая конструкция bash 4+/5+ в install.sh прикрыта развилкой по версии.

    Правило про КЛАСС: список в :data:`MODERN` - это образцы конструкций, а не адреса
    известных мест. Новая конструкция, вписанная без развилки, краснеет так же, как
    краснела бы первая.
    """
    assert _offenders(SCRIPT) == [], (
        "на маке штатный bash 3.2, и под set -u такая строка убивает установку на месте"
    )


def test_the_text_guard_reddens_on_a_construct_it_was_never_shown() -> None:
    """Отрицательная проба сторожа: он ловит форму, а не запомненные строки install.sh.

    Ни одного из этих обрывков в install.sh нет и не было. Последний - тот же класс,
    но ВНУТРИ развилки: сторож, который краснеет всегда, доказывает не больше, чем
    сторож, который всегда зелен.
    """
    prefix = "#!/usr/bin/env bash\nset -u\n"
    for sample, why in (
        ("local -A seen\n", "ассоциативный массив"),
        ("mapfile -t rows < /etc/hosts\n", "mapfile"),
        ('printf "%s" "${name^^}"\n', "смена регистра"),
        ("coproc helper { cat; }\n", "coproc"),
        ("now=$EPOCHSECONDS\n", "часы bash 5"),
    ):
        assert _offenders(prefix + sample), f"сторож не увидел {why}"
    guarded = prefix + "if (( UI_HAS_EPOCH )); then\n    now=$EPOCHSECONDS\nelse\n    now=0\nfi\n"
    assert _offenders(guarded) == [], "сторож краснеет и на прикрытом месте"


def _old_bash() -> str | None:
    """Путь к настоящему bash младше 4, если он на этой машине есть.

    Версия СПРАШИВАЕТСЯ у бинаря, а не выводится из имени файла: `bash-3.2` в PATH
    вполне бывает обёрткой над свежим bash, и тогда прибор мерил бы не то.
    """
    named = os.environ.get("TORRCAST_BASH32", "")
    candidates = [named] if named else []
    candidates += [shutil.which(name) or "" for name in ("bash-3.2", "bash3.2", "bash32")]
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            answer = subprocess.run(
                [candidate, "-c", "printf %s ${BASH_VERSINFO[0]}"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except OSError:
            continue
        if answer.stdout.strip().isdigit() and int(answer.stdout.strip()) < 4:
            return candidate
    return None


def _pty_dry_run(shell: str, seconds: int) -> tuple[int, str]:
    """Холостая подача заставки в настоящем pty под названным интерпретатором.

    Холостая - потому что мерить надо РИСОВАЛКУ: работник ей заменён на спящий, а
    канал прогресса, знаменатель, полоса, посадка и итоговый экран те же самые.
    Побочно это снимает вопрос песочницы: холостая подача не ставит ничего.
    """
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    child = subprocess.Popen(
        [shell, str(SCRIPT_PATH), str(seconds)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm-256color", "LINES": str(ROWS), "COLUMNS": str(COLS)},
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
        if time.monotonic() - started > seconds * 8 + 30:
            child.kill()
            break
    os.close(master)
    return child.wait(), stream.decode("utf-8", errors="replace")


@pytest.mark.machine
def test_the_splash_draws_itself_whole_under_a_real_old_bash() -> None:
    """Заставка под настоящим bash 3.2 доходит до конца и говорит «готово».

    Мера - КАДР и код возврата, а не отсутствие слова «ошибка»: рисовалка, умершая на
    первой строке, тоже ничего не печатает. Поэтому сверяется и число кадров, и рамка,
    и закрывающая строка, и чистота потока от жалоб интерпретатора.
    """
    shell = _old_bash()
    if shell is None:
        pytest.skip(
            "старого bash на машине нет: живого замера под bash 3.2 в этом прогоне НЕ БЫЛО, "
            "остался только текстовый разбор. Собрать 3.2.57 и назвать путь в TORRCAST_BASH32"
        )
    code, stream = _pty_dry_run(shell, DRY_SECONDS)
    assert code == 0, f"заставка под {shell} вернула {code}:\n{stream[-2000:]}"
    for complaint in (
        "unbound variable",
        "invalid timeout specification",
        "bad substitution",
        "syntax error",
        "not found",
        "invalid option",
    ):
        assert complaint not in stream, f"{shell} пожаловался «{complaint}»:\n{stream[-2000:]}"
    frames = stream.count(SYNC_ON)
    assert frames >= 20, f"кадров {frames}: заставка оборвалась, мерить не на чем"
    screen = pyte.Screen(COLS, ROWS)
    pyte.Stream(screen).feed(stream)
    shown = "\n".join(screen.display)
    assert "installed successfully" in shown, f"нет закрывающей строки:\n{shown}"
    assert "╭" in shown and "╰" in shown, f"рамка не дорисована:\n{shown}"
