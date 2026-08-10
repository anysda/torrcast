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
    return {
        "commit": git("rev-parse", "HEAD"),
        "date": git("log", "-1", "--format=%cI"),
        "dirty": bool(dirty) if dirty is not None else None,
        "fingerprint": mark,
        "files": count,
    }


def passport(tool: str, inputs: list[Path], argv: list[str]) -> dict[str, Any]:
    """Собрать паспорт прогона: чем считали и по какому сырью. Вывод добавит :func:`write`."""
    return {
        "tool": tool,
        "made": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "argv": argv,
        "probe": {"name": f"{tool}.py", "sha256": digest(ROOT / "scripts" / f"{tool}.py")},
        "code": code_stamp(),
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
    mark = code["fingerprint"][:12] if code["fingerprint"] else "кода рядом нет"
    dirty = " + несохранённые правки" if code["dirty"] else ""
    corpus = ", ".join(
        f"{Path(item['path']).name} ({item['lines']} строк, {item['sha256'][:12]})"
        for item in card["inputs"]
    )
    return (
        f"Паспорт прогона: {card['tool']}, {card['made']}; код {who}{dirty}, "
        f"отпечаток {mark}; сырьё: {corpus}"
    )
