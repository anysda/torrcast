#!/usr/bin/env python3
"""Сводка прогона по корпусу запросов: КАЖДЫЙ вердикт в своей колонке.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/runreport.py path/to/res.jsonl
    python scripts/runreport.py res.jsonl --by kind --by epoch --out report.md

Сырьё прогона в репе не лежит: снимается отдельно, путь передаётся аргументом. Одна
строка файла - один запрос; обязательны ``query`` и ``verdict``, остальное
(``why``, ``kind``, ``epoch``, ``src``, ``res``, ``views``) считается по наличию.
Разделы СКЛАДЫВАЮТСЯ, а не выбираются: строка с ``views`` добавляет таблицу
доступности и ничего не отменяет (:func:`report`).

Первой строкой сводки идёт ПАСПОРТ: коммит и отпечаток кода, отпечаток сырья, дата,
версия щупа (:mod:`runpass`); с ``--out`` он же ложится рядом отдельным файлом
``<сводка>.passport.json``. Сводка без паспорта непроверяема: пересчитать её нечем.

🔴 Колонки задаёт САМО СЫРЬЁ, а не список в коде, и сумма колонок сверяется с числом
строк на каждой таблице (:func:`tally`). Прежний счёт знал пять вердиктов, а прогон
раскладывал строки по восьми: на тысяче запросов 70 строк (7 %) не попадали ни в одну
колонку и ни в один процент, причём молча - таблица просто не сходилась с собственным
столбцом «всего», и заметить это можно было только сложив числа глазами. Отсюда
правило: неизвестный вердикт получает свою колонку, строка без вердикта - тоже, а
расхождение это исключение, а не мелкий шрифт под таблицей.

Классификацию щуп не трогает: вердикт читается таким, каким его записал прогон.
Переклейка вердиктов по тексту отказа - это уже методика, а не счёт, и место ей в том,
кто прогон ведёт.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import runpass

#: Порядок колонок: сначала успех, потом отказы от «нашли, но не сыграли» к «не нашли».
#: Список НЕ ограничивает счёт - он только сортирует; вердикт, которого тут нет, встанет
#: в конец своей колонкой.
LABELS: dict[str, str] = {
    "ok": "играбельно",
    "badrelease": "релиз негоден",
    "deadswarm": "рой мёртв",
    "swarmsilent": "рой молчит",
    "notried": "очередь не дошла",
    "notfound": "не найдено",
    "timeout": "таймаут",
    "other": "прочее",
}

#: Чем подписана строка, у которой поля ``verdict`` нет вовсе. Такие строки в колонку
#: тоже идут: «мы этого не разобрали» - тоже число, и прятать его нельзя.
NO_VERDICT = "(нет вердикта)"

#: Верх колонки «играбельно»: доля именно этого вердикта и есть публикуемый процент.
GOOD = "ok"


class CountMismatchError(RuntimeError):
    """Сумма колонок не сошлась с числом строк: счёт потерял вердикт."""


def verdict_of(row: dict[str, Any]) -> str:
    """Вердикт строки; пустой или отсутствующий - :data:`NO_VERDICT`, а не пропуск."""
    value = row.get("verdict")
    return str(value) if isinstance(value, str) and value else NO_VERDICT


def verdicts_in(rows: list[dict[str, Any]]) -> list[str]:
    """Все вердикты сырья в порядке :data:`LABELS`; незнакомые - в конец по алфавиту."""
    seen = {verdict_of(row) for row in rows}
    return [v for v in LABELS if v in seen] + sorted(seen - set(LABELS))


def tally(rows: list[dict[str, Any]], verdicts: list[str], where: str = "всего") -> Counter[str]:
    """Разложить строки по вердиктам и СВЕРИТЬ сумму колонок с числом строк.

    Сверка тут, а не в глазах читателя: ровно на этом месте прежний счёт и терял
    выборку. Расхождение - :class:`CountMismatchError`, потому что дальше считать нечего:
    все проценты ниже делятся на число, которое колонки уже не описывают.
    """
    counts = Counter(verdict_of(row) for row in rows)
    total = sum(counts[v] for v in verdicts)
    if total != len(rows):
        lost = sorted(set(counts) - set(verdicts))
        raise CountMismatchError(
            f"{where}: колонки дают {total}, строк {len(rows)}; "
            f"вне колонок остались {', '.join(lost) or '-'}"
        )
    return counts


def dedup(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Один запрос - одна строка: побеждает последняя (прогон перезапускали)."""
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        seen[str(row.get("query", ""))] = row
    return list(seen.values()), len(rows) - len(seen)


def share(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "-"


def head(verdicts: list[str]) -> list[str]:
    names = " | ".join(f"{LABELS.get(v, v)} ({v})" for v in verdicts)
    align = "|".join("---:" for _ in verdicts)
    return [f"| группа | всего | {names} | доля {GOOD} |", f"|---|---:|{align}|---:|"]


def table(title: str, groups: dict[str, list[dict[str, Any]]], verdicts: list[str]) -> list[str]:
    """Таблица «группа × вердикт»; каждая строка проверена :func:`tally` на сходимость."""
    out = [f"\n### {title}\n", *head(verdicts)]
    for name, rows in groups.items():
        if not rows:
            continue
        counts = tally(rows, verdicts, where=f"{title} / {name}")
        cells = " | ".join(str(counts[v]) for v in verdicts)
        out.append(f"| {name} | {len(rows)} | {cells} | {share(counts[GOOD], len(rows))} |")
    return out


def grouped(rows: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    """Разложить строки по значению поля; отсутствующее значение - своя группа «(нет)»."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = row.get(field)
        groups.setdefault(str(value) if value not in (None, "") else "(нет)", []).append(row)
    return dict(sorted(groups.items()))


def picture_id(view: dict[str, Any]) -> tuple[Any, Any, Any] | None:
    """Личность выбранной картины ОДНОЙ формы - ``(имя, год, вид)`` - из любого JSONL.

    Форм у поля ``default`` две: список ``[имя, год, вид]`` у щупов замера и словарь у
    :func:`poolreplay.as_json`. Возвращать их как есть нельзя: список давал 3-кортеж, а
    словарь - свой, и вид в них стоял на разных местах или отсутствовал вовсе, так что
    смешение форм ВНУТРИ одной строки не совпадало никогда, молча и стопроцентно.
    Неназванный вид - это ``None``, а не отсутствие члена: длину кортежа задаёт код,
    а не то, сколько полей случилось в сырье.
    """
    value = view.get("default")
    if isinstance(value, list | tuple) and len(value) >= 2:
        parts = (*value[:3], None, None)
        return (parts[0], parts[1], parts[2])
    if isinstance(value, dict) and value.get("title") is not None:
        return (value.get("title"), value.get("year"), value.get("kind"))
    return None


def same_picture(one: tuple[Any, Any, Any] | None, other: tuple[Any, Any, Any] | None) -> bool:
    """Одна ли это картина; вид сверяется, только если его назвали ОБЕ стороны.

    Вид знает не всякая форма (``as_json`` до TC-529 его не писал вовсе), и требовать
    его от обеих значило бы записать в потери каждую строку старого формата. Расплата
    названа: пока вид не назван, фильм и сериал одного имени и года неразличимы.
    """
    if one is None or other is None:
        return False
    if one[:2] != other[:2]:
        return False
    return one[2] is None or other[2] is None or one[2] == other[2]


def off_top(view: dict[str, Any]) -> bool:
    """Сказал ли сам прогон, что дефолт пришёл НЕ с первой строки меню.

    Старые выдачи звали это поле ``requested_picture_playable`` - имя было неверным
    (см. :func:`availability`), а считало оно ровно это, поэтому читаем оба ключа.

    Строки, где играть было нечего вовсе, сюда не идут: где дефолта нет, там нечему
    расходиться с верхом меню, а щуп пишет в это поле ``False`` и на них тоже - иначе
    мёртвая строка показывала бы 99 расхождений из 99 на пустом месте.
    """
    if not view.get("any_picture_playable", view.get("playable")):
        return False
    told = view.get("default_is_menu_top", view.get("requested_picture_playable"))
    return told is False


def availability(rows: list[dict[str, Any]], base: str) -> list[dict[str, Any]]:
    """Честный счёт доступности: осталась ли играть ТА КАРТИНА, что выбрал эталон.

    🔴 Спрошенная картина - это выбор ЭТАЛОННОЙ строки, а не верх меню, и меряется он
    только сравнением строк между собой. Прежде счёт верил полю самого прогона, а поле
    отвечало на другой вопрос - «совпал ли дефолт с первой строкой меню», - и эталон
    показывал 23 потери из 99 там, где их не может быть по построению: эталон сравнивают
    сам с собой. Все 23 оказались законным правилом «первая ЖИВАЯ часть» (TC-529): верх
    меню Титаник 1943 года при мёртвом рое, фильм «Фарго» 1996-го на запрос про третий
    сезон. Ноль на эталонной строке теперь не совпадение, а свойство счёта.

    Расхождение дефолта с верхом меню при этом не прячется: оно считается отдельно
    (:func:`off_top`) и стоит в таблице своей колонкой. Законно оно или нет - вопрос уже
    не к доступности, а к тому, ту ли картину вообще выбрал эталон; на это нужен корпус
    с размеченным правильным ответом, которого нет.
    """
    labels = list(rows[0].get("views", {})) if rows else []
    out: list[dict[str, Any]] = []
    for label in labels:
        asked = any_picture = requested_picture = default_off_top = 0
        for row in rows:
            views = row.get("views")
            if not isinstance(views, dict):
                continue
            baseline, current = views.get(base), views.get(label)
            if not isinstance(baseline, dict) or not isinstance(current, dict):
                continue
            wanted = picture_id(baseline)
            if wanted is None:
                continue
            asked += 1
            any_picture += bool(current.get("any_picture_playable", current.get("playable")))
            requested_picture += same_picture(picture_id(current), wanted)
            default_off_top += off_top(current)
        out.append(
            {
                "label": label,
                "asked": asked,
                "any_picture_playable": any_picture,
                "requested_picture_playable": requested_picture,
                "default_off_top": default_off_top,
            }
        )
    return out


def availability_report(rows: list[dict[str, Any]]) -> list[str]:
    """Таблица трёх разных вопросов, чтобы ни один не выдавался за другой."""
    if not rows or not isinstance(rows[0].get("views"), dict):
        return []
    labels = list(rows[0]["views"])
    base = "ВСЕ (эталон)" if "ВСЕ (эталон)" in labels else labels[0]
    out = [
        "\n### Доступность спрошенной картины\n",
        f"Спрошенная картина - выбор строки «{base}»; на ней самой потерь ноль по построению.",
        "Колонка «дефолт не с верха меню» - не потери: дефолт франшизы это первая ЖИВАЯ часть.\n",
        "| набор | запросов | сыграло что-нибудь | сыграла спрошенная картина | потерь "
        "| дефолт не с верха меню |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in availability(rows, base):
        lost = item["asked"] - item["requested_picture_playable"]
        out.append(
            f"| {item['label']} | {item['asked']} | {item['any_picture_playable']} | "
            f"{item['requested_picture_playable']} | {lost} | {item['default_off_top']} |"
        )
    return out


def report(rows: list[dict[str, Any]], repeats: int, fields: list[str]) -> list[str]:
    """Сводка сырья: КАЖДЫЙ раздел, который по нему считается, и ни одним меньше.

    🔴 Раздел, который сырьё не кормит, выходит пустым и молча пропадает - раздел,
    который кормит, обязан быть. Прежде наличие ключа ``views`` у ПЕРВОЙ строки
    возвращало одну лишь таблицу доступности, а вердикты, честный HD, разрезы ``--by``
    и причины отказов выбрасывались молча; строка с обоими видами полей сразу показала
    бы половину правды и ничем бы об этом не сообщила (TC-529). Форма сырья тут не
    переключатель, а набор слагаемых: два вида полей в одной строке дают два раздела.
    """
    verdicts = verdicts_in(rows)
    counts = tally(rows, verdicts)
    n = len(rows)
    out = [f"Запросов: **{n}**" + (f" (свернуто повторов: {repeats})" if repeats else "") + "\n"]
    for verdict in verdicts:
        mark = "" if verdict in LABELS else "  ← вердикт незнакомый, колонка заведена по сырью"
        out.append(
            f"- {LABELS.get(verdict, verdict)} (`{verdict}`): "
            f"**{counts[verdict]}** ({share(counts[verdict], n)}){mark}"
        )
    out.append(f"\nСверка: сумма колонок {sum(counts.values())} = строк {n}.\n")
    out.extend(availability_report(rows))

    known = [r for r in rows if isinstance(r.get("res"), int)]
    oks = [r for r in rows if verdict_of(r) == GOOD]
    if known:
        hd = [r for r in oks if int(r["res"]) >= 720]
        named = [r for r in oks if isinstance(r.get("res"), int)]
        out.append(
            f"Честный HD (≥720p) среди «{LABELS[GOOD]}»: **{len(hd)}** из {len(named)} "
            f"названных ({share(len(hd), len(named))}); разрешения не назвали "
            f"{len(oks) - len(named)}.\n"
        )

    for field in fields:
        table_rows = table(f"По полю «{field}»", grouped(rows, field), verdicts)
        out.extend(table_rows)

    bad = [r for r in rows if verdict_of(r) != GOOD]
    reasons = Counter(f"{verdict_of(r)}: {r.get('why') or '-'}" for r in bad)
    out.append(f"\n### Причины отказов, всего {len(bad)}\n")
    out.append("| вердикт: причина | шт |")
    out.append("|---|---:|")
    out.extend(f"| {why} | {count} |" for why, count in reasons.most_common())
    return out


def load(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="сводка прогона: все вердикты в колонках")
    ap.add_argument("jsonl", type=Path, nargs="+", help="сырьё прогона (res.jsonl)")
    ap.add_argument("--by", action="append", default=[], help="поле для разреза (kind, epoch)")
    ap.add_argument("--out", type=Path, help="куда положить сводку (markdown)")
    ap.add_argument("--keep-repeats", action="store_true", help="не сворачивать перезапуски")
    args = ap.parse_args(argv)
    cmdline = list(argv) if argv is not None else sys.argv[1:]

    rows = load(args.jsonl)
    repeats = 0
    if not args.keep_repeats:
        rows, repeats = dedup(rows)
    # Паспорт идёт первой строкой самой сводки: пересчитать её потом нечем, если не
    # знать, каким кодом и по какому сырью её сделали.
    card = runpass.passport("runreport", args.jsonl, cmdline)
    text = "\n".join([runpass.told(card), "", *report(rows, repeats, args.by)])
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        text += f"\n\nпаспорт прогона: {runpass.write(card, args.out)}"
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
