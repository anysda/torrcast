"""Щупы из ``scripts/``: мерить продукт вправе только тот, у кого сходится счёт.

Оба щупа читают сырьё, которого в репе нет (прогоны и выдачи снимаются отдельно), - и
проверяются они не на нём, а на маленьких выдуманных выдачах. Проверяется ровно то, из-за
чего оба щупа и заведены: что ни одна строка не пропадает молча.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import torrcast
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
            [
                "Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO",
                "a" * 40,
                int(8.2 * GB),
                60,
                "RuTor",
            ],
            [
                "Врата Штейна / Steins;Gate [2011, Япония, фантастика, WEB-DL 720p] MVO",
                "b" * 40,
                int(3.1 * GB),
                25,
                "RuTor",
            ],
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


def test_щуп_сохраняет_сиды_и_приговор_каждой_раздачи() -> None:
    """JSONL позволяет пересчитать очередь по строкам, а не только по общей сумме."""
    replay = probe("poolreplay")
    record = gates_pool()
    item = replay.replay(
        record["query"], replay.batches_of(record), tune(Config(), CAUTIOUS), CAUTIOUS
    )

    saved = replay.as_json(item)["plans"][0]
    releases = saved["release_verdicts"]
    assert len(releases) == saved["releases"] == 4
    assert {release["seeders"] for release in releases} == {9, 25, 40, 60}
    assert sum(release["queue"] is not None for release in releases) == saved["queue"]
    assert all(
        (release["queue"] is None) != (release["drop_reason"] is None) for release in releases
    )
    heavy = next(release for release in releases if release["seeders"] == 9)
    assert heavy["queue"] is None and heavy["drop_reason"] == "тяжелее потолка"


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
            [
                "Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO",
                "a" * 40,
                int(8.2 * GB),
                60,
                "RuTor",
            ],
            [
                "Криминальное чтиво / Pulp Fiction [1994, США, криминал, BDRip 1080p] MVO",
                "e" * 40,
                int(9.0 * GB),
                80,
                "RuTor",
            ],
        ],
    )
    item = replay.replay(
        record["query"], replay.batches_of(record), tune(Config(), CAUTIOUS), CAUTIOUS
    )
    assert item.pictures == 2 and len(item.menu) == 1
    assert [p.title for p in item.missed] == ["Криминальное чтиво"]


def written(path: Path) -> dict[str, Any]:
    """Паспорт, положенный щупом рядом с его выводом."""
    card = path.with_name(path.name + ".passport.json")
    assert card.exists(), f"щуп не оставил паспорта рядом с {path.name}"
    loaded = json.loads(card.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_отпечаток_кода_меняется_вместе_с_кодом(tmp_path: Path) -> None:
    """Отпечаток считается по самим файлам: git на стенде может и не приехать."""
    runpass = probe("runpass")
    assert runpass.fingerprint(tmp_path) == (None, 0), "кода рядом нет - и отпечатка нет"

    (tmp_path / "torrcast").mkdir()
    (tmp_path / "torrcast" / "parse.py").write_text("x = 1\n", encoding="utf-8")
    before, count = runpass.fingerprint(tmp_path)
    assert count == 1 and before is not None
    (tmp_path / "torrcast" / "parse.py").write_text("x = 2\n", encoding="utf-8")
    assert runpass.fingerprint(tmp_path)[0] != before, "правка кода не изменила отпечаток"


def test_паспорт_называет_путь_импортированного_пакета() -> None:
    """Запуск по пути не скрывает, если Python взял пакет из другого дерева."""
    runpass = probe("runpass")
    card = runpass.passport("runreport", [], [])
    package = str(Path(torrcast.__file__).resolve().parent)
    assert card["code"]["package"] == package
    assert f"пакет {package}" in runpass.told(card)


def test_счёт_кладёт_паспорт_рядом_со_сводкой(tmp_path: Path) -> None:
    """Сводка называет код и сырьё - иначе её нечем пересчитать."""
    report = probe("runreport")
    runpass = probe("runpass")
    raw = tmp_path / "res.jsonl"
    raw.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows_of(*ALL_VERDICTS)) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    assert report.main([str(raw), "--out", str(out)]) == 0

    assert out.read_text(encoding="utf-8").startswith("Паспорт прогона: runreport")
    card = written(out)
    assert card["tool"] == "runreport"
    assert card["probe"]["sha256"] == runpass.digest(SCRIPTS / "runreport.py")
    assert card["code"]["fingerprint"] == runpass.fingerprint()[0]
    assert card["inputs"] == [runpass.about(raw)]
    assert card["inputs"][0]["lines"] == len(ALL_VERDICTS)
    assert card["output"]["sha256"] == runpass.digest(out)


def test_щуп_отбора_кладёт_паспорт_рядом_с_разбором(tmp_path: Path) -> None:
    """Разбор пулов подписан тем же паспортом: два замера сравнивают отпечатки, не память."""
    replay = probe("poolreplay")
    runpass = probe("runpass")
    pools = tmp_path / "pools.jsonl"
    pools.write_text(json.dumps(gates_pool(), ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "replay.jsonl"
    assert replay.main([str(pools), "--jsonl", str(out)]) == 0

    card = written(out)
    assert card["tool"] == "poolreplay"
    assert card["probe"]["sha256"] == runpass.digest(SCRIPTS / "poolreplay.py")
    assert card["code"]["fingerprint"] == runpass.fingerprint()[0]
    assert card["inputs"] == [runpass.about(pools)]
    assert card["output"] == runpass.about(out)
    assert card["argv"] == [str(pools), "--jsonl", str(out)]
