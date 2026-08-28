#!/usr/bin/env python3
"""Паспорт прогона: чем считали, каким кодом и по какому сырью.

Инструмент разработчика: в устанавливаемый пакет не входит. Отдельной командой не
зовётся - паспорт пишут сами щупы (``poolreplay.py``, ``runreport.py``) рядом со своим
выводом, файлом ``<вывод>.passport.json``.

🔴 Замер без паспорта - не замер. Сохранённые прогоны лежали без единой отметки о коде:
ни коммита, ни даты, ни отпечатка, - и два прогона сравнивались только по памяти того,
кто их заказывал. Ровно на этом сорвалась сверка щупа с прежним замером: отличить
«щуп считает иначе» от «код с тех пор изменился» было нечем.

Что паспорт обязан пережить: сырьё и код уезжают на машину, где нет ни репозитория, ни
git (код копируют каталогом). Поэтому код называется ДВАЖДЫ - коммитом, если он
известен, и отпечатком :func:`fingerprint`, который считается по самим файлам и потому
есть всегда. Совпал отпечаток - это тот же код, что бы ни говорил коммит.

Пути в паспорт попадают такими, какими их назвали в командной строке: паспорт лежит
рядом с сырьём и описывает то место, где сырьё снято.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Приписка к имени вывода. Рядом с ``res.jsonl`` ляжет ``res.jsonl.passport.json``:
#: сырьё и паспорт не разъедутся при копировании по маске.
SUFFIX = ".passport.json"

#: Корень репозитория (или каталога, куда код скопировали): у щупов он один - родитель
#: ``scripts/``.
ROOT = Path(__file__).resolve().parent.parent

#: Что считается «кодом продукта» для отпечатка. Щуп зовёт эти модули, и от них зависит
#: каждое число прогона.
#:
#: 🔴 Звёздочка тут ДВОЙНАЯ, и это не украшение. С одинарной отпечаток брал ровно верхний
#: уровень пакета - один файл из 887, - а весь продукт лежит подпакетами. Правка правила
#: подгруза, выкладки или профиля отпечаток НЕ двигала, и паспорт прогона уверял, что код
#: тот же самый, чем бы он ни отличался. Проверяется это отрицательной пробой
#: (``tests/test_runpass.py``): меняем файл в подпакете - отпечаток обязан уехать.
CODE_GLOB = "torrcast/**/*.py"

#: Что в отпечаток не идёт: кэш байт-кода не код, а его тень, и живёт он своей жизнью.
CODE_SKIP = "__pycache__"

#: Сколько ждать git. Его может не быть вовсе (код приехал каталогом) - это не беда.
GIT_TIMEOUT = 10


def digest(path: Path) -> str:
    """sha256 файла: единственная отметка, которая не врёт при копировании."""
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            sha.update(chunk)
    return sha.hexdigest()


def lines_in(path: Path) -> int:
    """Строк в файле - столько запросов и было в прогоне, если это jsonl."""
    with path.open("rb") as fh:
        return sum(1 for line in fh if line.strip())


def about(path: Path) -> dict[str, Any]:
    """Описание одного файла: путь, размер, строки, отпечаток."""
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "lines": lines_in(path),
        "sha256": digest(path),
    }


def git(*args: str) -> str | None:
    """Спросить git о репозитории; его отсутствие - обычное дело, а не ошибка."""
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def fingerprint(root: Path = ROOT) -> tuple[str | None, int]:
    """Отпечаток кода продукта: sha256 по парам «имя файла - его sha256».

    Считается по файлам, а не по git: на стенде код лежит копией, а сравнивать прогоны
    надо и там. Одинаковый отпечаток - одинаковый код, разный - искать разницу можно
    пофайлово.

    ⚠️ В пару берётся путь ОТ КОРНЯ, а не имя файла: одних только совпадающих имён в
    пакете полтора десятка (``freeze.py``, ``doctor.py``, ``__init__.py`` и прочие), и на
    голых именах два разных файла складывались бы в отпечаток неотличимо - перенос модуля
    между подпакетами не сдвинул бы его вовсе.
    """
    files = sorted(p for p in root.glob(CODE_GLOB) if CODE_SKIP not in p.parts)
    if not files:
        return None, 0
    sha = hashlib.sha256()
    for path in files:
        sha.update(f"{path.relative_to(root).as_posix()}:{digest(path)}\n".encode())
    return sha.hexdigest(), len(files)


def code_stamp() -> dict[str, Any]:
    """Чем считали: коммит с датой, если git под рукой, и отпечаток - всегда."""
    mark, count = fingerprint()
    dirty = git("status", "--porcelain", "--", CODE_GLOB.split("/")[0])
    spec = importlib.util.find_spec("torrcast")
    package = (
        str(Path(spec.origin).resolve().parent)
        if spec is not None and spec.origin is not None
        else None
    )
    return {
        "commit": git("rev-parse", "HEAD"),
        "date": git("log", "-1", "--format=%cI"),
        "dirty": bool(dirty) if dirty is not None else None,
        "fingerprint": mark,
        "files": count,
        "package": package,
    }


def probe_file(tool: str, probe: Path | None = None) -> Path | None:
    """Где лежит сам щуп: названный путь, свой ``scripts/`` или файл запущенной команды.

    🔴 TC-430. Разовый щуп пишется под один замер и живёт на стенде рядом с сырьём, а не в
    ``scripts/`` репы, - и паспорт требуется как раз ему: ради таких прогонов щупы и
    заводят. Пока файл искали только в ``scripts/``, такой вызов падал ``FileNotFoundError``,
    и паспорт собирали руками из тех же кирпичей - каждый по-своему.

    Нашлось ничего - ``None``, и отпечаток щупа в паспорте будет пустым. Паспорт без одной
    отметки читается, а упавший паспорт не читается вовсе.
    """
    guesses = [probe] if probe is not None else []
    guesses.append(ROOT / "scripts" / f"{tool}.py")
    # argv[0] - это и есть запущенный щуп; чужие точки входа (pytest, python -c) сюда не
    # попадают: у них нет расширения .py, и выдавать их за щуп нельзя.
    running = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if running is not None and running.suffix == ".py":
        guesses.append(running)
    for path in guesses:
        if path.is_file():
            return path.resolve()
    return None


def probe_stamp(tool: str, probe: Path | None = None) -> dict[str, Any]:
    """Чем мерили: имя щупа и его отпечаток. Файла не нашлось - имя по названию, без sha."""
    found = probe_file(tool, probe)
    if found is None:
        return {"name": f"{tool}.py", "sha256": None}
    return {"name": found.name, "sha256": digest(found)}


@dataclass(frozen=True)
class Fit:
    """Годен ли САМ прогон: были ли живы приборы, которыми он снят.

    🔴 TC-867. Паспорт до сих пор удостоверял только КОД и СЫРЬЁ - то есть чем считали, -
    и молчал о том, работал ли прибор. Прогон, чей журнал приёмника оборвался на второй
    секунде, выглядел в паспорте ровно как прогон с живым журналом, и «голоданий ноль»
    уезжало из него в отчёт неотличимо от заработанного нуля.
    """

    ok: bool
    why: str


def passport(
    tool: str,
    inputs: list[Path],
    argv: list[str],
    probe: Path | None = None,
    fit: Fit | None = None,
) -> dict[str, Any]:
    """Собрать паспорт прогона: чем считали и по какому сырью. Вывод добавит :func:`write`.

    ``probe`` - путь к самому щупу, если он лежит не в ``scripts/`` (разовый щуп на стенде).
    Не назвали - :func:`probe_file` найдёт его сам.

    ``fit`` - годность самого прогона, если щуп её меряет. Не назвали - паспорт скажет об
    этом вслух (:func:`told`), а не промолчит: незаявленная годность и подтверждённая
    годность обязаны читаться по-разному.
    """
    return {
        "tool": tool,
        "made": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "argv": argv,
        "probe": probe_stamp(tool, probe),
        "code": code_stamp(),
        "fit": None if fit is None else {"ok": fit.ok, "why": fit.why},
        "inputs": [about(path) for path in inputs],
        "output": None,
    }


def write(card: dict[str, Any], output: Path) -> Path:
    """Дописать в паспорт отпечаток уже записанного вывода и положить паспорт рядом с ним."""
    card["output"] = about(output)
    target = output.with_name(output.name + SUFFIX)
    target.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def told(card: dict[str, Any]) -> str:
    """Одна строка паспорта для человека: чем считали и по какому сырью."""
    code = card["code"]
    who = code["commit"][:12] if code["commit"] else "не из git"
    # Подпись и её пустой случай складываются в ОДНУ фразу: «отпечаток кода рядом нет» и
    # «пакет пакет не найден» человек читает как опечатку, а не как «неизвестно».
    mark = code["fingerprint"][:12] if code["fingerprint"] else "не посчитан (кода рядом нет)"
    package = code.get("package") or "не найден"
    dirty = " + несохранённые правки" if code["dirty"] else ""
    corpus = ", ".join(
        f"{Path(item['path']).name} ({item['lines']} строк, {item['sha256'][:12]})"
        for item in card["inputs"]
    )
    # Годность называется ВСЕГДА, и её отсутствие - тоже слово: молчащая строка читается
    # как «годен», а это ровно та подмена, из-за которой мёртвый прибор попадал в отчёт.
    fit = card.get("fit")
    if fit is None:
        fitness = "годность прогона не заявлена"
    else:
        fitness = f"{'ГОДЕН' if fit['ok'] else 'БРАК'}: {fit['why']}"
    return (
        f"Паспорт прогона: {card['tool'] or 'щуп не назван'}, "
        f"{card['made'] or 'дата не записана'}; "
        f"код {who}{dirty}, отпечаток {mark}, пакет {package}; "
        f"{fitness}; "
        f"сырьё: {corpus or 'не записано'}"
    )
