"""Щупы из ``scripts/``: мерить продукт вправе только тот, у кого сходится счёт.

Оба щупа читают сырьё, которого в репе нет (прогоны и выдачи снимаются отдельно), - и
проверяются они не на нём, а на маленьких выдуманных выдачах. Проверяется ровно то, из-за
чего оба щупа и заведены: что ни одна строка не пропадает молча.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from torrcast.cli import Args
from torrcast.profile import CAUTIOUS, tune
from torrcast.state import Config

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
GB = 1024**3

#: Все вердикты, которыми прогон подписывает запрос. Пять из них счёт знал и раньше, три
#: (``deadswarm``/``swarmsilent``/``notried``) приехали, когда отказ «рой у них мёртв»
#: развели на три разных, - и вот их-то таблицы и потеряли.
ALL_VERDICTS = (
    "ok",
    "badrelease",
    "deadswarm",
    "swarmsilent",
    "notried",
    "notfound",
    "timeout",
    "other",
)


def probe(name: str) -> ModuleType:
    """Загрузить щуп из ``scripts/``: пакетом каталог не является, зато путь известен."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # без записи в sys.modules ломается @dataclass
    spec.loader.exec_module(module)
    return module


def rows_of(*verdicts: str) -> list[dict[str, Any]]:
    return [{"query": f"q{i}", "verdict": v, "kind": "movie"} for i, v in enumerate(verdicts)]


def test_счёт_разносит_все_вердикты_прогона() -> None:
    """Восемь вердиктов в сырье - восемь колонок, и сумма их равна числу строк."""
    report = probe("runreport")
    rows = rows_of(*ALL_VERDICTS)
    verdicts = report.verdicts_in(rows)
    assert verdicts == list(ALL_VERDICTS)
    assert sum(report.tally(rows, verdicts).values()) == len(rows)

    text = "\n".join(report.report(rows, 0, ["kind"]))
    for verdict in ALL_VERDICTS:
        assert f"`{verdict}`" in text, f"вердикт {verdict} не назван ни одной строкой сводки"
    line = next(ln for ln in text.splitlines() if ln.startswith("| movie |"))
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    total, columns = int(cells[1]), [int(c) for c in cells[2 : 2 + len(verdicts)]]
    assert sum(columns) == total == len(rows)


def test_потерянный_вердикт_роняет_счёт() -> None:
    """Колонок меньше, чем вердиктов в сырье, - это исключение, а не сноска под таблицей."""
    report = probe("runreport")
    rows = rows_of("ok", "deadswarm", "swarmsilent", "notried")
    with pytest.raises(report.CountMismatchError) as beef:
        report.tally(rows, ["ok"])
    said = str(beef.value)
    assert "deadswarm" in said and "swarmsilent" in said and "notried" in said


def test_незнакомый_вердикт_получает_свою_колонку() -> None:
    """Вердикт, которого щуп не знает, и строка вовсе без вердикта считаются наравне."""
    report = probe("runreport")
    rows = [*rows_of("ok", "невиданное"), {"query": "q9", "kind": "movie"}]
    verdicts = report.verdicts_in(rows)
    assert "невиданное" in verdicts and report.NO_VERDICT in verdicts
    assert sum(report.tally(rows, verdicts).values()) == len(rows)


def pool(query: str, **rows: list[list[Any]]) -> dict[str, Any]:
    return {"query": query, "rows": rows}


def gates_pool() -> dict[str, Any]:
    """Выдача одной картины двумя именами: русским с годом и латинским без года."""
    return pool(
        "врата штейна",
        RuTor=[
            ["Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO",
             "a" * 40, int(8.2 * GB), 60, "RuTor"],
            ["Врата Штейна / Steins;Gate [2011, Япония, фантастика, WEB-DL 720p] MVO",
             "b" * 40, int(3.1 * GB), 25, "RuTor"],
        ],
        Knaben=[
            ["Steins;Gate BDRip 1080p x264 AAC", "c" * 40, int(7.4 * GB), 40, "Knaben"],
            ["Steins;Gate BDRemux 2160p HEVC", "d" * 40, int(60 * GB), 9, "Knaben"],
        ],
    )


def test_щуп_прогоняет_отбор_по_сохранённой_выдаче() -> None:
    """Живых служб не надо ни одной: пул с диска доезжает до очереди кандидатов."""
    replay = probe("poolreplay")
    record = gates_pool()
    item = replay.replay(
        record["query"], replay.batches_of(record), tune(Config(), CAUTIOUS), CAUTIOUS
    )
    assert item.raw_rows == 4
    assert item.menu and item.top is not None and item.default is not None
    assert item.top.title == "Врата Штейна"

    plan = item.plans[0]
    queue, drops = replay.verdicts(plan, Args(query=record["query"].split()))
    assert queue, "очередь кандидатов пуста - отбор до релизов не дошёл"
    assert plan.ranked[queue[0] - 1].seeders == 60, "дефолтом стал не верх ранжира"
    # Ровно та сверка, ради которой щуп и заведён: очередь плюс отсев = пул картины.
    assert len(queue) + sum(drops.values()) == len(plan.picture.releases)
    assert "тяжелее потолка" in drops, "2160p-ремукс обязан быть отсеян по битрейту"


def test_щуп_называет_склейку_двух_имён() -> None:
    """Сколько кучек свелось в картину, видно щупу - иначе «три в одной» не сосчитать."""
    replay = probe("poolreplay")
    record = gates_pool()
    item = replay.replay(
        record["query"], replay.batches_of(record), tune(Config(), CAUTIOUS), CAUTIOUS
    )
    assert len(item.merges) == 1
    members, picture = item.merges[0]
    assert len(members) == 2
    assert {p.title for p in members} == {"Врата Штейна", "Steins;Gate"}
    assert len(picture.releases) == sum(len(p.releases) for p in members) == 4


def test_щуп_называет_кого_не_пустил_в_меню() -> None:
    """Каталог знает картину, а меню её не показывает - это приговор, и он назван."""
    replay = probe("poolreplay")
    record = pool(
        "врата штейна",
        RuTor=[
            ["Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO",
             "a" * 40, int(8.2 * GB), 60, "RuTor"],
            ["Криминальное чтиво / Pulp Fiction [1994, США, криминал, BDRip 1080p] MVO",
             "e" * 40, int(9.0 * GB), 80, "RuTor"],
        ],
    )
    item = replay.replay(
        record["query"], replay.batches_of(record), tune(Config(), CAUTIOUS), CAUTIOUS
    )
    assert item.pictures == 2 and len(item.menu) == 1
    assert [p.title for p in item.missed] == ["Криминальное чтиво"]
