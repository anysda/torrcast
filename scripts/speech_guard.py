"""Сторож речи: каждое авто-решение, о котором сценарий говорит человеку, сторожится.

Мера тут одна и она не статическая: надпись ЗАМЕНЯЕТСЯ литералом ``"MUT"``, и дошедшие до
неё тесты обязаны покраснеть. Упоминание ключа в тестах мерить нечем - оно врёт в обе
стороны: ключ бывает назван рядом и ни разу не проверен, а проверен бывает через целую
строку вывода, где ключа не видно.

🔴 Список исключений здесь не заводится. Сторож, севший на ненулевое число и закрытый
именным перечнем, это правило, закрытое константой: дерево перестаёт двигаться к нулю, а
гейт продолжает светить зелёным.

Прогонов не 92, а по числу групп: места, чьи наборы дошедших тестов НЕ ПЕРЕСЕКАЮТСЯ,
мутируются разом, и упавший тест однозначно указывает на своё место. Пересекись наборы -
и падение нельзя было бы приписать, поэтому пересечение и разводит места по группам.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from speech_sites import Site, fingerprint, mutated, sites

#: Куда быстрый набор гейта кладёт карту досягаемости (см. :mod:`speech_reach`).
REACH_DIR = Path(os.environ.get("SPEECH_REACH_OUT", ".speech-reach"))
#: Журнал восстановления: он же признак прерванного прогона.
JOURNAL = Path(".speech-guard-restore.json")
_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.MULTILINE)


def _reach(stamp: str) -> dict[int, set[str]]:
    """Карта досягаемости, снятая С ЭТОГО дерева. Не сошёлся отпечаток - отказ."""
    parts = sorted(REACH_DIR.glob("*.json")) if REACH_DIR.is_dir() else []
    if not parts:
        raise SystemExit(
            f"сторож речи: карты досягаемости нет в {REACH_DIR}/.\n"
            "Её снимает быстрый набор гейта. Мерить нечем - это отказ, а не зелень."
        )
    found: dict[int, set[str]] = {}
    for part in parts:
        data = json.loads(part.read_text(encoding="utf-8"))
        if data.get("stamp") != stamp:
            raise SystemExit(
                f"сторож речи: карта {part} снята с другого дерева "
                f"({data.get('stamp')} против {stamp}). Прогони быстрый набор заново."
            )
        for key, tests in data["hits"].items():
            found.setdefault(int(key), set()).update(t for t in tests if t != "<импорт>")
    return found


def _groups(found: list[Site], reach: dict[int, set[str]]) -> list[list[int]]:
    """Разбить места на группы с попарно непересекающимися наборами тестов."""
    order = sorted((i for i in range(len(found)) if reach.get(i)), key=lambda i: -len(reach[i]))
    taken: list[set[str]] = []
    batches: list[list[int]] = []
    for index in order:
        for number, used in enumerate(taken):
            if not used & reach[index]:
                taken[number] |= reach[index]
                batches[number].append(index)
                break
        else:
            taken.append(set(reach[index]))
            batches.append([index])
    return batches


#: С какого размера группы окупается раздача по ядрам: ниже него подъём воркеров дороже
#: самого прогона. Замерено на этом дереве: 173,8 с в один поток против 88,0 с.
SPREAD_FROM = 12


def _run(nodeids: list[str]) -> set[str]:
    """Прогнать тесты и вернуть имена тех, кто среагировал (упал или сломался)."""
    spread = ["-n", "4"] if len(nodeids) >= SPREAD_FROM else []
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=no",
            "-rfE",
            "-p",
            "no:cacheprovider",
            "--no-header",
            *spread,
            *nodeids,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return set(_FAILED.findall(proc.stdout))


def _restore(saved: dict[str, str]) -> None:
    for path, text in saved.items():
        Path(path).write_text(text, encoding="utf-8")
    JOURNAL.unlink(missing_ok=True)


def _recover() -> None:
    """Прерванный прогон мог оставить дерево мутированным - вернуть его молча нельзя."""
    if not JOURNAL.exists():
        return
    saved: dict[str, str] = json.loads(JOURNAL.read_text(encoding="utf-8"))
    print(f"сторож речи: прошлый прогон оборван, возвращаю {len(saved)} файл(ов)", flush=True)
    _restore(saved)


def _mutated_file(text: str, found: list[Site], batch: list[int], path: Path) -> str:
    """Заменить надписи всех мест группы, попавших в ОДИН файл, разом и с конца."""
    mine = [i for i in batch if Path(found[i].path) == path]
    for index in sorted(mine, key=lambda i: (found[i].span.line, found[i].span.col), reverse=True):
        text = mutated(text, found[index])
    return text


def main() -> int:
    _recover()
    root = Path.cwd()
    found = sites(root)
    reach = _reach(fingerprint(found))
    bare = [i for i in range(len(found)) if not reach.get(i)]
    started = time.monotonic()
    batches = _groups(found, reach)
    for batch in batches:
        saved = {
            str(root / found[i].path): (root / found[i].path).read_text(encoding="utf-8")
            for i in batch
        }
        JOURNAL.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        try:
            for path, text in saved.items():
                broken = _mutated_file(text, found, batch, Path(path).relative_to(root))
                assert broken != text, f"склейка ничего не заменила в {path}"
                Path(path).write_text(broken, encoding="utf-8")
            reacted = _run(sorted({t for i in batch for t in reach[i]}))
        finally:
            _restore(saved)
        bare += [i for i in batch if not (reach[i] & reacted)]
    seconds = time.monotonic() - started
    print(
        f"сторож речи: мест {len(found)}, прогонов {len(batches)}, "
        f"{seconds:.1f} с, голых {len(bare)}"
    )
    for index in sorted(bare):
        site = found[index]
        why = "ни один тест не доходит" if not reach.get(index) else "мутация не покраснела"
        print(f"  ГОЛОЕ {site.where} {site.sink} {list(site.keys)} - {why}")
    if bare:
        print(
            "\nНадпись можно стереть, и дерево останется зелёным. Порог тут не двигают:\n"
            "место закрывается тестом, который сравнивает сказанное с phrase(<ключ>)."
        )
    return 1 if bare else 0


if __name__ == "__main__":
    raise SystemExit(main())
