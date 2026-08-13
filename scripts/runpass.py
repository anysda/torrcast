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
CODE_GLOB = "torrcast/*.py"

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
    """
    files = sorted(root.glob(CODE_GLOB))
    if not files:
        return None, 0
    sha = hashlib.sha256()
    for path in files:
        sha.update(f"{path.name}:{digest(path)}\n".encode())
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


def passport(
    tool: str, inputs: list[Path], argv: list[str], probe: Path | None = None
) -> dict[str, Any]:
    """Собрать паспорт прогона: чем считали и по какому сырью. Вывод добавит :func:`write`.

    ``probe`` - путь к самому щупу, если он лежит не в ``scripts/`` (разовый щуп на стенде).
    Не назвали - :func:`probe_file` найдёт его сам.
    """
    return {
        "tool": tool,
        "made": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "argv": argv,
        "probe": probe_stamp(tool, probe),
        "code": code_stamp(),
        "inputs": [about(path) for path in inputs],
        "output": None,
    }


#: Чем восстановленный паспорт отличается от снятого: его собрали задним числом по описи,
#: а не написал щуп в момент прогона. Отметка стоит в самом паспорте, чтобы это отличие
#: нельзя было потерять при копировании.
RESTORED = "восстановлен по описи, не снят вместе с прогоном"


def restore(
    output: Path,
    told_by: str,
    tool: str | None = None,
    made: str | None = None,
    inputs: list[Path] | None = None,
) -> dict[str, Any]:
    """Паспорт задним числом для прогона, снятого БЕЗ паспорта.

    🔴 TC-431. Правило «паспорт рядом с каждым прогоном» появилось позже самих прогонов, и
    архив ему не соответствует. Прогон без паспорта нельзя привязать ни к коду, ни к
    сырью: его числа приходится либо перепроверять целиком, либо брать на веру.

    Восстановить можно не всё, и это главное свойство такого паспорта. Отпечаток и число
    строк САМОГО прогона считаются по файлу и потому честны - ими прогон и опознаётся
    после любого копирования. Код, которым считали, по описи чаще всего назвать нечем -
    он и остаётся пустым, а не выдуманным: неизвестное перечислено списком ``unknown``.

    ``told_by`` - откуда взято остальное (строка описи, каталог замера). Форма паспорта та
    же, что у снятого: старые глаза читают его без оговорок, а отметка :data:`RESTORED`
    не даёт спутать восстановленное со снятым.
    """
    card: dict[str, Any] = {
        "tool": tool,
        "made": made,
        "python": None,
        "argv": None,
        "probe": {"name": f"{tool}.py" if tool else None, "sha256": None},
        "code": {
            "commit": None,
            "date": None,
            "dirty": None,
            "fingerprint": None,
            "files": 0,
            "package": None,
        },
        "inputs": [about(path) for path in inputs or []],
        "output": about(output),
        "restored": {"how": RESTORED, "told_by": told_by},
    }
    blank = [name for name, value in card.items() if value is None]
    blank += [f"code.{name}" for name, value in card["code"].items() if value is None]
    blank += [f"probe.{name}" for name, value in card["probe"].items() if value is None]
    if not card["inputs"]:
        blank.append("inputs")
    card["restored"]["unknown"] = sorted(blank)
    return card


def write(card: dict[str, Any], output: Path) -> Path:
    """Дописать в паспорт отпечаток уже записанного вывода и положить паспорт рядом с ним."""
    card["output"] = about(output)
    target = output.with_name(output.name + SUFFIX)
    target.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def told(card: dict[str, Any]) -> str:
    """Одна строка паспорта для человека: чем считали и по какому сырью.

    У восстановленного паспорта (:func:`restore`) это сказано первым же словом: пустое в
    нём значит «неизвестно», а не «нечего сказать», и путать их нельзя.
    """
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
    head = "Паспорт прогона (восстановлен)" if card.get("restored") else "Паспорт прогона"
    return (
        f"{head}: {card['tool'] or 'щуп не назван'}, {card['made'] or 'дата не записана'}; "
        f"код {who}{dirty}, отпечаток {mark}, пакет {package}; "
        f"сырьё: {corpus or 'не записано'}"
    )
