"""Щупы из ``scripts/``: мерить продукт вправе только тот, у кого сходится счёт.

Оба щупа читают сырьё, которого в репе нет (прогоны и выдачи снимаются отдельно), - и
проверяются они не на нём, а на маленьких выдуманных выдачах. Проверяется ровно то, из-за
чего оба щупа и заведены: что ни одна строка не пропадает молча.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import socket
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import tests.usecases.choice.world as world
import torrcast
from torrcast.adapters.chromecast.profile_detector import ProfileDetector, detector
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.domain.tune import tune

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


def test_упаковщики_щупов_сверяют_хвост_с_сеткой() -> None:
    """Щуп не вправе принимать код возврата ffmpeg за готовность куска."""
    for name in ("gridcheck", "recodebench"):
        tree = ast.parse((SCRIPTS / f"{name}.py").read_text(encoding="utf-8"))
        starts = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "Packer"
            and node.func.attr == "start"
        ]
        assert starts, f"{name}: не найден ни один запуск упаковщика"
        for call in starts:
            grids = [word.value for word in call.keywords if word.arg == "grid"]
            assert len(grids) == 1 and isinstance(grids[0], ast.Name) and grids[0].id == "grid", (
                f"{name}:{call.lineno}: упаковщик не получил сетку щупа"
            )


def rows_of(*verdicts: str) -> list[dict[str, Any]]:
    return [{"query": f"q{i}", "verdict": v, "kind": "movie"} for i, v in enumerate(verdicts)]


def test_щуп_берёт_профиль_из_паспорта_приёмника_и_называет_причину(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Паспорт действует по умолчанию: профиль щупа - тот же, что взял бы показ.

    Паспорт спрашивается у устройства, а устройства тут нет, поэтому опрос приезжает
    заводом приёмника (``ProfileDetector(ask=...)``) - тем же доводом, которым его
    подменяет и зеркало самого паспорта.
    """
    choose = probe("probeprofile").choose

    def answers(address: str, timeout: float = 0.0) -> Device:
        return Device(address, maker="Sony", model="BRAVIA", name="Android TV")

    tuned, choice = choose(Config(tv="receiver.local"), None, ProfileDetector(ask=answers).detect)
    said = capsys.readouterr().out

    assert choice.profile is ANDROID_TV
    assert "профиль приёмника: androidtv" in said and "by passport:" in said
    assert tuned == tune(Config(tv="receiver.local"), ANDROID_TV)


def test_щуп_отдаёт_ручной_профиль_вперёд_паспорта_и_говорит_об_этом(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--profile`` сильнее паспорта и виден в отчёте прогона, а не только в коде.

    Идёт это через настоящий вход щупа: назвать профиль руками и не увидеть его в
    отчёте - ровно тот случай, когда сравнивают два прогона, снятых по разным правилам.
    """
    replay = probe("poolreplay")
    pools = tmp_path / "pools.jsonl"
    pools.write_text("", encoding="utf-8")
    save_config(Config(tv="receiver.local"))

    detector.forget()
    assert replay.main([str(pools), "--profile", "q70d"]) == 0
    said = capsys.readouterr().out
    detector.forget()

    assert "профиль приёмника: q70d" in said and "manually named" in said


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
    assert "heavier than the ceiling" in drops, "2160p-ремукс обязан быть отсеян по битрейту"


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
    assert heavy["queue"] is None and heavy["drop_reason"] == "heavier than the ceiling"


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


def franchise_pool() -> dict[str, Any]:
    """Две части одной франшизы: обе с планом, обе в меню."""
    return pool(
        "матрица",
        RuTor=[
            [
                "Матрица / The Matrix [1999, США, фантастика, BDRip 1080p] MVO",
                "a" * 40,
                int(9.0 * GB),
                90,
                "RuTor",
            ],
            [
                "Матрица: Перезагрузка / The Matrix Reloaded [2003, США, BDRip 1080p] MVO",
                "b" * 40,
                int(9.4 * GB),
                70,
                "RuTor",
            ],
        ],
    )


def test_верх_меню_это_то_что_видит_человек() -> None:
    """Картина без плана в меню не печатается - и «верхом меню» её звать нельзя."""
    replay = probe("poolreplay")
    record = franchise_pool()
    item = replay.replay(
        record["query"], replay.batches_of(record), tune(Config(), CAUTIOUS), CAUTIOUS
    )
    assert [p.title for p in item.menu] == ["Матрица", "Матрица: Перезагрузка"]
    assert len(item.plans) == 2 and not item.above_default

    # У первой картины меню пул отбора пуст: человек увидит списком одну «Перезагрузку».
    empty = replay.Replay(
        query=item.query,
        raw_rows=item.raw_rows,
        results=item.results,
        catalog=item.catalog,
        menu=item.menu,
        plans=item.plans[1:],
    )
    assert [p.title for p in empty.above_default] == ["Матрица"]
    said = replay.brief(empty)
    assert said.index("Матрица: Перезагрузка") < said.index("без плана и не в меню")
    assert "→ Enter" not in said, "щуп обещает выбор там, где человек списка не увидит"

    told = "\n".join(replay.detail(empty, 5, 3))
    assert "[-] Матрица (1999" in told, "беспланная картина не вправе носить номер меню"
    assert "[1] Матрица: Перезагрузка" in told, "номер пункта считается по планам"


def test_щуп_спрашивает_пул_другим_запросом() -> None:
    """«Тот же пул, другой номер части» - флагом, а не обвязкой вокруг щупа."""
    replay = probe("poolreplay")
    assert replay.asks_of("матрица", []) == ["матрица"]
    assert replay.asks_of("матрица", ["{}", "{} 2", "дюна"]) == ["матрица", "матрица 2", "дюна"]

    record = franchise_pool()
    config = tune(Config(), CAUTIOUS)
    asked = replay.replay("матрица 2", replay.batches_of(record), config, CAUTIOUS, pool="матрица")
    # Пул тот же, вопрос другой - и ответ другой: в меню осталась одна вторая часть.
    assert asked.pool == "матрица" and asked.query == "матрица 2"
    assert [p.title for p in asked.menu] == ["Матрица: Перезагрузка"]
    assert replay.as_json(asked)["pool"] == "матрица"


def test_щуп_называет_ступени_за_первым_кругом() -> None:
    """Гейт добора сработал - щуп говорит об этом, а не выдаёт первый круг за весь поиск."""
    replay = probe("poolreplay")
    record = gates_pool()
    item = replay.replay(
        record["query"], replay.batches_of(record), tune(Config(), CAUTIOUS), CAUTIOUS
    )
    # Пул тощий, и боевой поиск ушёл бы за вторым именем в справку - щуп туда не ходит.
    assert item.beyond == ["паспорт"]
    assert replay.as_json(item)["beyond"] == ["паспорт"]
    told = "\n".join(replay.beyond_report([item]))
    assert "паспорт            1 из 1" in told
    assert "опоздавшая выдача" in told, "путь, которого не видно вовсе, обязан быть назван"


def test_щуп_помнит_кто_отдал_полную_страницу() -> None:
    """Гейт потолка спрашивает у клиента полные страницы - и в пуле они сохранились."""
    replay = probe("poolreplay")
    page = [["Девять ярдов / The Whole Nine Yards", "f" * 40, GB, 5, "RuTor"]]
    assert replay.capped_of(pool("девять", RuTor=page * 100, Knaben=page)) == ("RuTor",)
    assert replay.capped_of(pool("девять", RuTor=page * 99)) == ()
    assert replay.asked_nobody(("RuTor",)).capped == ("RuTor",)


def test_доступность_не_засчитывает_соседнюю_картину() -> None:
    """«Сыграло что-нибудь» остаётся отдельно и не выдаётся за ответ на запрос."""
    report = probe("runreport")
    rows = [
        {
            "query": "дюна",
            "views": {
                "ВСЕ (эталон)": {"playable": True, "default": ["Дюна 2", 2024, "movie"]},
                "без источника": {"playable": True, "default": ["Дюна", 2021, "movie"]},
            },
        }
    ]
    counts = report.availability(rows, "ВСЕ (эталон)")
    changed = counts[1]
    assert changed["any_picture_playable"] == 1
    assert changed["requested_picture_playable"] == 0
    text = "\n".join(report.report(rows, 0, []))
    assert "| без источника | 1 | 1 | 0 | 1 | 0 |" in text


def test_эталонная_строка_не_теряет_картин_по_построению() -> None:
    """Эталон сравнивают сам с собой: потерь там нет, чем бы ни кончился отбор.

    🔴 Прежде счёт верил полю прогона `requested_picture_playable`, а оно отвечало на
    вопрос «дефолт совпал с верхом меню» - и эталон показывал 23 потери из 99 (TC-529).
    Все 23 были законным «первая ЖИВАЯ часть»: у верха меню мёртвый рой или нет
    спрошенной серии. Прибором, который врёт на собственном нуле, мерить нельзя.
    """
    report = probe("runreport")
    views: dict[str, dict[str, Any]] = {
        # дефолт пришёл не с верха меню (там Титаник 1943 с мёртвым роем)
        "ВСЕ (эталон)": {
            "any_picture_playable": True,
            "requested_picture_playable": False,
            "default": ["Титаник", 1997, "movie"],
        },
        "без источника": {
            "any_picture_playable": True,
            "default": ["Титаник", 1997, "movie"],
        },
    }
    rows = [{"query": "титаник", "views": views}]
    base, other = report.availability(rows, "ВСЕ (эталон)")
    assert base["asked"] - base["requested_picture_playable"] == 0, "эталон потерял картину"
    assert base["default_off_top"] == 1, "расхождение с верхом меню спрятано, а не отделено"
    assert other["asked"] - other["requested_picture_playable"] == 0

    # Играть было нечего: дефолта нет, расходиться с верхом меню нечему.
    views["всё мертво"] = {
        "any_picture_playable": False,
        "requested_picture_playable": False,
        "default": None,
    }
    empty = report.availability(rows, "ВСЕ (эталон)")[2]
    assert empty["asked"] - empty["requested_picture_playable"] == 1, "мёртвая строка не потеря"
    assert empty["default_off_top"] == 0, "мёртвая строка сочтена расхождением с верхом меню"


def test_картина_узнаётся_в_любой_форме_записи() -> None:
    """Список щупа и словарь `as_json` - одна картина, а не две.

    🔴 Прежде список отдавал ``(имя, год, вид)``, а словарь свой кортеж без вида, и при
    смешении форм ВНУТРИ одной строки картины не совпадали НИКОГДА (TC-529): счёт
    записывал в потери всё подряд, молча и стопроцентно. Вид сверяется, только когда его
    назвали обе стороны, иначе строки старого формата теряются целиком.
    """
    report = probe("runreport")
    listed = report.picture_id({"default": ["Дюна", 2021, "movie"]})
    dictated = report.picture_id({"default": {"title": "Дюна", "year": 2021, "releases": 7}})
    kinded = report.picture_id({"default": {"title": "Дюна", "year": 2021, "kind": "movie"}})
    short = report.picture_id({"default": ["Дюна", 2021]})
    assert len(listed) == len(dictated) == len(short) == 3, "формы дают кортежи разной длины"
    assert report.same_picture(listed, dictated), "вид без пары не должен разводить картины"
    assert report.same_picture(listed, kinded) and report.same_picture(listed, short)
    assert not report.same_picture(listed, report.picture_id({"default": ["Дюна", 2021, "tv"]}))
    assert not report.same_picture(listed, report.picture_id({"default": ["Дюна", 1984, "movie"]}))

    rows = [
        {
            "query": "дюна",
            "views": {
                "ВСЕ (эталон)": {"any_picture_playable": True, "default": ["Дюна", 2021, "movie"]},
                "без источника": {
                    "any_picture_playable": True,
                    "default": {"title": "Дюна", "year": 2021, "releases": 3},
                },
            },
        }
    ]
    changed = report.availability(rows, "ВСЕ (эталон)")[1]
    assert changed["requested_picture_playable"] == 1, (
        "та же картина в другой форме сочтена потерей"
    )


def test_сводка_на_строках_с_видами_не_теряет_остальных_разделов() -> None:
    """Строка несёт и вердикт, и виды - сводка обязана дать оба раздела, а не выбрать.

    🔴 Прежде ключ ``views`` у ПЕРВОЙ строки возвращал одну таблицу доступности, а
    вердикты, разрезы ``--by`` и причины отказов молча пропадали (TC-529). Замер, который
    показывает половину правды и не говорит об этом, хуже замера, которого нет.
    """
    report = probe("runreport")
    views = {"ВСЕ (эталон)": {"playable": True, "default": ["Дюна", 2021, "movie"]}}
    rows = [
        {"query": "дюна", "verdict": "ok", "res": 1080, "seg": "кино", "views": views},
        {"query": "арракис", "verdict": "notfound", "why": "пусто", "seg": "кино"},
    ]
    text = "\n".join(report.report(rows, 0, ["seg"]))
    assert "### Доступность спрошенной картины" in text
    assert "играбельно (`ok`): **1**" in text, "вердикты выброшены"
    assert "Честный HD" in text, "честный HD выброшен"
    assert "### По полю «seg»" in text, "разрез --by выброшен"
    assert "### Причины отказов" in text, "таблица причин выброшена"


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


def test_паспорт_выписывается_щупу_вне_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Разовый щуп живёт рядом с сырьём, а не в репе, - и паспорт нужен как раз ему."""
    runpass = probe("runpass")
    one_off = tmp_path / "oneoff.py"
    one_off.write_text("# разовый щуп\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(one_off)])

    card = runpass.passport("oneoff", [], [])
    assert card["probe"] == {"name": "oneoff.py", "sha256": runpass.digest(one_off)}
    assert runpass.passport("названный", [], [], probe=one_off)["probe"]["sha256"] == (
        runpass.digest(one_off)
    )


def test_паспорт_молчит_об_отпечатке_щупа_а_не_падает(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Щупа не нашлось нигде: паспорт без одной отметки читается, упавший - нет."""
    runpass = probe("runpass")
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "нет-такого.py")])
    card = runpass.passport("нет-такого", [], [])
    assert card["probe"] == {"name": "нет-такого.py", "sha256": None}
    assert card["code"]["fingerprint"] == runpass.fingerprint()[0]


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


def test_щуп_не_считает_картинкой_слово_приёмника() -> None:
    """Стоящий указатель - это не кадр, как бы приёмник ни назвал своё состояние.

    🔴 Замер на живом Q70D: ``PLAYING`` приходит за 0-6 с до первого кадра, и щуп, веривший
    слову, занижал старт ровно на эти секунды. Порог сдвига берётся от МЕСТА ЗАХОДА:
    продолжение с середины стартует с ненулевого указателя, и «больше нуля» там истинно
    ещё до всякой картинки.
    """
    tv = probe("tvprobe")

    assert not tv.shown(0.0, 0.0)  # холодный старт: приёмник сказал «играю», кадра нет
    assert not tv.shown(300.0, 300.0)  # продолжение: указатель стоит на месте захода
    assert not tv.shown(300.1, 300.0)  # дрожание на месте кадром не считаем
    assert tv.shown(0.5, 0.0)
    assert tv.shown(300.5, 300.0)


def test_щуп_показа_не_отвечает_нулём_на_прогоне_без_картинки() -> None:
    """🔴 Прогон, где кадра не было вовсе, обязан быть виден по КОДУ ВОЗВРАТА.

    Замер на живой приставке: Hi10P нашей упаковкой не пошёл, указатель все 90 с простоял
    на месте захода - а щуп вышел нулём, потому что приёмник не бросил исключения и
    отвечал ``PLAYING``. В пакетном прогоне такой отказ читался как пройденный.
    """
    tv = probe("tvprobe")

    assert tv.clean(3.8, [])
    assert not tv.clean(None, []), "картинки не было - это не чистый прогон"
    assert not tv.clean(3.8, [(0.0, 89.6)]), "подвис при живом запасе - тоже не чистый"

    # 🔴 TC-867. Третья половина вердикта - про ПРИБОР: чистая картинка при оборванном
    # журнале приёмника это не чистый прогон, а замер с одним выключенным прибором.
    journal = probe("tvjournal")
    torn = journal.life(WINDOW, WINDOW + 400.0, _journal(WINDOW, [0.0, 0.2, 0.4]))
    alive = journal.life(WINDOW, WINDOW + 400.0, _journal(WINDOW, [i * 5.0 for i in range(81)]))

    assert not torn.fit and alive.fit, "проба опирается на разные вердикты журнала"
    assert tv.clean(3.8, [], alive)
    assert not tv.clean(3.8, [], torn), "оборванный журнал - брак замера, а не чистый прогон"


def test_щуп_перемотки_ловит_негодную_фикстуру_вслух() -> None:
    """Материал без опорных кадров щуп называет сам, а не мерит на нём бессмыслицу.

    🔴 Фикстура ``tape.mkv`` со стенда: на шаге 10 с карта дала 9 сегментов, первый длиной
    2901.8 с. Сетка при этом построена честно, ругаться
    :func:`torrcast.adapters.stream_pack.grid_for.grid_for` не на что, - и щуп молча мерил перемотку
    по одному получасовому куску. Кто брал эту фикстуру, получал числа ни о чём и не знал об этом.
    """
    from torrcast.adapters.stream_pack.grid import Grid

    seek = probe("seekcheck")
    bounds = (0.0, 2901.8, *(2901.8 + 10.0 * k for k in range(1, 8)))
    tape = Grid(bounds, 2981.8, True)

    assert tape.count == 9, "та самая сетка: девять кусков, первый - в полчаса"
    unfit = seek.unfit_grid(tape, 10.0)
    assert "v0" in unfit and "2901.8" in unfit, f"негодность обязана быть названа числами: {unfit}"

    assert not seek.unfit_grid(Grid.uniform(600.0, 10.0), 10.0), "ровная сетка годна"
    short = Grid((0.0, 10.0, 20.0), 30.0, True)
    assert "3 сегментов" in seek.unfit_grid(short, 10.0), "трёх кусков сеточному замеру мало"


def test_правка_сетки_щупом_не_теряет_ленту_и_вес() -> None:
    """🔴 Щуп обязан мерить ту же упаковку после ручной правки границ."""
    tv = probe("tvprobe")

    def weigh(_a: float, _b: float) -> float:
        return 42.0

    base = tv.Grid((0.0, 10.0, 20.0), 30.0, True, weigh, 0.103)
    args = SimpleNamespace(
        bounds="",
        url="film",
        duration=30.0,
        step=10.0,
        uniform=False,
        ceiling=0.0,
        mbit=0.0,
        recode=False,
        drop="10",
        add="11",
    )

    changed = tv.make_grid(args, CAUTIOUS, grid_for=lambda *_a, **_k: base)

    assert changed.bounds == (0.0, 11.0, 20.0)
    assert changed.weigh is weigh, "щуп потерял предсказатель веса"
    assert changed.origin == 0.103, "щуп потерял общее смещение ленты"


def test_явные_границы_щупа_берут_начало_ленты() -> None:
    """Бисект границ режет ту же ленту фильма, что и штатная сетка."""
    tv = probe("tvprobe")
    asked: list[str] = []

    def origin(url: str) -> float:
        asked.append(url)
        return 0.103

    args = SimpleNamespace(
        bounds="10,20",
        url="film",
        duration=30.0,
        step=10.0,
        uniform=False,
        ceiling=0.0,
        mbit=0.0,
        recode=False,
        drop="",
        add="",
    )

    grid = tv.make_grid(args, CAUTIOUS, pack_origin=origin)

    assert asked == ["film"]
    assert grid.bounds == (0.0, 10.0, 20.0)
    assert grid.origin == 0.103, "явная сетка потеряла начало общей ленты фильма"


@pytest.mark.machine
def test_щуп_перемотки_берёт_порт_у_ядра() -> None:
    """Два замера рядом на одном стенде - не ``Address already in use``.

    🔴 Порты 18098/18099 стояли в щупе числами, и параллельные прогоны были невозможны
    вовсе: второй падал на ``bind``, причём не по делу замера.
    """
    seek = probe("seekcheck")
    source = Path(seek.__file__ or "").read_text(encoding="utf-8")
    # Номер порта ищем в КОДЕ, а не в тексте: в докстринге прежние 18098/18099 названы
    # нарочно - чтобы следующий не завёл их снова.
    numbers = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, int)
    }

    assert not [n for n in numbers if 1024 <= n <= 65535], "порт снова прибит числом"
    port = seek.free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))  # ядро отдало свободный - его и занимаем
        assert sock.getsockname()[1] == port


#: Щупы, собирающие упаковку под живой приёмник, и что каждая сборка обязана взять у
#: профиля. Ключ - имя класса, значение - «довод сборки → поле профиля».
#:
#: ``packbench`` и ``seambench`` сюда не входят намеренно: приёмника у них нет вовсе,
#: они меряют механику упаковщика на локальном файле и профиля не спрашивают.
PACK_FROM_PROFILE = {
    "Feed": {
        "wait": "hold_seconds",
        "cap": "max_segment_bytes",
        "container": "segment_container",
    },
    "Recoder": {
        "cap": "max_segment_bytes",
        "container": "segment_container",
    },
}
PACK_PROBES = ("tvprobe", "seekcheck", "seekbench")


def _assignments(tree: ast.Module) -> dict[str, list[str]]:
    """Все присваивания простым именам: имя → выражения, которые в него кладут.

    Нужны, чтобы довод-псевдоним (``container=container``) читался по своему источнику, а
    не по имени: имя само по себе не говорит ничего.
    """
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                found.setdefault(target.id, []).append(ast.unparse(node.value))
    return found


def test_щупы_упаковки_берут_пороги_и_контейнер_у_профиля() -> None:
    """Потолок веса, удержание запроса и контейнер кусков - свойства ПРИЁМНИКА, не щупа.

    🔴 Пока оба профиля были по 16 МБ и оба резали mpegts, расхождение не проявлялось.
    Когда у приставки потолок стал 28 МБ, а контейнер - fmp4, щуп строил сетку под 28
    (профиль в ``layout`` он передавал честно), а раздачу собирал с осторожными
    умолчаниями: на релизе, чьи копии тяжелее 16 МБ, ни один кусок не выкладывался, и
    здоровый продукт выглядел «ни кадра».

    🔴 TC-868. Контейнер оборвался ровно так же и молча: ``--profile androidtv`` менял
    надпись, но щуп всё равно отдавал приставке mpegts - то есть мерил CMAF-тракт,
    ни разу его не тронув. Прежний сторож этого не поймал, потому что смотрел на один
    щуп из трёх и на одну сборку из двух.

    Показ берёт все три числа у профиля
    (:func:`torrcast.usecases.playback._tract._tract`,
    :func:`torrcast.usecases.playback._recoder._recoder`) - щуп обязан мерить тот же тракт.
    """
    blind = []
    checked = 0
    for name in PACK_PROBES:
        tree = ast.parse((SCRIPTS / f"{name}.py").read_text(encoding="utf-8"))
        known = _assignments(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            wanted = PACK_FROM_PROFILE.get(node.func.id)
            if wanted is None:
                continue
            given = {kw.arg: ast.unparse(kw.value) for kw in node.keywords}
            for argument, field in wanted.items():
                checked += 1
                said = given.get(argument)
                # Довод либо прямо называет поле профиля, либо кладёт имя, КАЖДОЕ
                # присваивание которому названо тем же полем.
                sources: list[str] = [] if said is None else known.get(said, [said])
                if not sources or not all(f"profile.{field}" in text for text in sources):
                    blind.append(
                        f"{name}.py:{node.lineno} {node.func.id}: "
                        f"{argument} = {said} - не профиль ({field})"
                    )
        # Приёмнику контейнер называется не доводом сборки, а полем: подсказка формата
        # в LOAD - последнее звено того же провода, и рвётся оно так же молча.
        if "ChromecastReceiver(" in ast.unparse(tree):
            checked += 1
            named = [
                ast.unparse(node.value)
                for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Attribute)
                and node.targets[0].attr == "segment_container"
            ]
            behind = [text for one in named for text in known.get(one, [one])]
            if not behind or not all("profile.segment_container" in text for text in behind):
                blind.append(f"{name}.py: приёмнику контейнер не назван ({named or 'ничего'})")
    assert checked >= 9, "сторож обязан проверить обе сборки и приёмник у каждого щупа"
    assert not blind, "провод профиля оборван:\n" + "\n".join(blind)


def test_щупы_упаковки_подписывают_прогон_прибором() -> None:
    """🔴 Прогон, который не назвал прибор, отвечает на «чем снято» историей git.

    TC-870: семь чисел приставки простояли в дереве без единой отметки о приборе, и
    восстанавливать их пришлось коммитами - а коммит прибора не называет тем более.
    Подпись обязана печататься самим щупом (:func:`probestamp.stamp`), брать место у
    этого прогона, а не из литерала исходника, и обязана нести
    ТРАКТ: профиль, заявленный надписью, и контейнер, реально уехавший приёмнику,
    разъезжались молча (TC-868), и число тогда снято не про тот тракт.
    """
    mute = []
    for name in PACK_PROBES:
        tree = ast.parse((SCRIPTS / f"{name}.py").read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "stamp"
        ]
        if not calls:
            mute.append(f"{name}.py: подписи прибора нет вовсе")
            continue
        for call in calls:
            said = [ast.unparse(argument) for argument in call.args]
            expected = [f"'{name}'", "container", "run_where(args.card)"]
            if said[:3] != expected:
                mute.append(f"{name}.py:{call.lineno}: подпись зовёт себя {said[:3]}")
            if len(said) < 4 or "приёмник {choice.profile.key}" not in said[3]:
                mute.append(f"{name}.py:{call.lineno}: профиль приёмника потерян в {said[3:]}")

    assert not mute, "щуп меряет молча:\n" + "\n".join(mute)


def test_щуп_берёт_код_из_своего_дерева() -> None:
    """Каждый щуп, зовущий продукт, кладёт впереди путей СВОЙ корень - и не чужой.

    🔴 Замер: ``voicedump.py`` этой строки не имел и брал ``torrcast`` из того дерева, на
    которое смотрит editable-установка венва (соседний клон), а паспорт прогона называл
    при этом коммит и отпечаток своего. Замер, снятый одним кодом и подписанный другим,
    невоспроизводим: соседний клон в параллельной волне меняют соседи.
    """
    root = "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))"
    guilty = []
    for path in sorted(SCRIPTS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        calls = any(
            line.strip().startswith(("from torrcast", "import torrcast"))
            for line in source.splitlines()
        )
        if calls and root not in source:
            guilty.append(path.name)

    assert not guilty, f"щуп берёт продукт из чужого дерева: {', '.join(guilty)}"


def widen_pools() -> list[dict[str, Any]]:
    """Тощая русская выдача одной части и латинская выдача всей франшизы к ней."""
    return [
        pool(
            "ледниковый период 3",
            RuTor=[
                [
                    "Ледниковый период 3: Эра динозавров / Ice Age 3 (2009) BDRip 1080p",
                    "a" * 40,
                    int(4.4 * GB),
                    30,
                    "RuTor",
                ]
            ],
        ),
        pool(
            "Ice Age",
            Knaben=[
                ["Ice Age 3 (2009) BDRip 1080p x264", "b" * 40, GB, 40, "K"],
                ["Ice Age (2002) BDRip 1080p x264", "c" * 40, GB, 55, "K"],
                ["Ice Age 2 The Meltdown (2006) BDRip 1080p x264", "d" * 40, GB, 35, "K"],
            ],
        ),
    ]


def test_щуп_добора_называет_цену_отказа_гейта() -> None:
    """🔴 Отказ добора без счёта привезённого - это приговор без предмета.

    Гейт добора стоит на числе привезённых картин, и одного вердикта «остаюсь на прежней
    выдаче» для замера мало: пока не сосчитано, СКОЛЬКО раздач спрошенной картины он этим
    выбросил, порог гейта не с чем сравнивать. Щуп обязан печатать обе стороны разом.
    """
    replay = probe("widenreplay")
    pools = {
        str(record["query"]).casefold(): replay.poolreplay.batches_of(record)
        for record in widen_pools()
    }
    ask = replay.facts_passport(None)
    item = replay.widen(
        "ледниковый период 3",
        pools,
        tune(Config(), CAUTIOUS),
        CAUTIOUS,
        lambda *_a, **_k: Origin(title="Ice Age", year=2002, name="Ледниковый период"),
    )

    assert item.worth and item.alt == "Ice Age" and not item.missed
    assert not item.taken, "гейт счёта картин этот добор отвергает - на нём щуп и заведён"
    assert (
        item.counts["строк после"] == 4 and item.counts["картин после"] > item.counts["картин до"]
    )
    assert item.counts["раздач после"] > item.counts["раздач до"], "цена отказа не сосчитана"
    assert any("brought more pictures" in note for note in item.notes)
    assert ask("нет такой картины") == Origin(), "без кэша справка молчит, а не выдумывает"


def same_picture_pools() -> list[dict[str, Any]]:
    """Тощая русская выдача и латинский добор в ТУ ЖЕ картину: ключи картин те же."""
    return [
        pool(
            "врата штейна",
            RuTor=[
                [
                    "Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO",
                    "a" * 40,
                    int(8.2 * GB),
                    60,
                    "RuTor",
                ]
            ],
        ),
        pool(
            "Steins;Gate",
            Knaben=[
                ["Steins;Gate BDRip 1080p x264 AAC", "c" * 40, int(7.4 * GB), 40, "Knaben"],
                ["Steins;Gate WEB-DL 1080p", "d" * 40, int(5.0 * GB), 25, "Knaben"],
            ],
        ),
    ]


def test_щуп_добора_читает_взятым_добор_в_те_же_картины() -> None:
    """🔴 Добор, добавивший раздачи в ТЕ ЖЕ картины, - взят, а не отказ.

    Прежняя редакция сверх расширения выдачи сверяла ещё и КЛЮЧИ картин: ключи те же -
    и взятый боевым гейтом добор записывался отвергнутым. Так щуп насчитал «9 доборов
    вместо 13»: проверка, которая не умеет краснеть на своём предмете, - это зелёный
    отчёт, купленный входом.
    """
    replay = probe("widenreplay")
    pools = {
        str(record["query"]).casefold(): replay.poolreplay.batches_of(record)
        for record in same_picture_pools()
    }
    item = replay.widen(
        "врата штейна",
        pools,
        tune(Config(), CAUTIOUS),
        CAUTIOUS,
        lambda *_a, **_k: Origin(title="Steins;Gate", year=2011, name="Врата Штейна"),
    )

    assert item.worth and item.alt == "Steins;Gate" and not item.missed
    assert item.taken, "боевой гейт этот добор берёт - и щуп обязан прочесть это взятием"
    # Взятый добор мерится итогом самого захода: картина осталась одна, чужих ноль.
    assert item.counts["картин после"] == item.counts["картин до"] == 1
    assert item.counts["раздач до"] == 1 and item.counts["раздач после"] == 3
    assert (item.plays["после"] or [None])[0] == "Врата Штейна"


def test_щуп_добора_читает_отказом_чужую_картину() -> None:
    """Раздач стало больше, а приехала другая картина - добора не было, и так и сказано.

    Вторая сторона пробы: щуп, зеленеющий на любой прибавке, свой предмет не мерит.
    Русская выдача держит «Восхождение» Шепитько, а латинское имя в ней - от
    одноимённого чужого кино: добор по нему везёт не тот фильм, и гейт обязан ответить
    «приехала другая картина». Справка тут молчит - имя добора ничем не подтверждено,
    и гейт строг ровно поэтому.
    """
    replay = probe("widenreplay")
    records = [
        pool(
            "восхождение",
            RuTor=[
                ["Восхождение (1976) BDRip 1080p", "a" * 40, int(8.0 * GB), 30, "RuTor"],
                [
                    "Восхождение / The Climbers [2019, Китай, приключения, WEB-DL 1080p]",
                    "e" * 40,
                    int(6.0 * GB),
                    20,
                    "RuTor",
                ],
            ],
        ),
        pool(
            "The Climbers",
            Knaben=[
                ["The Climbers 2019 BDRip 1080p x264", "b" * 40, int(7.0 * GB), 40, "Knaben"],
                ["The Climbers 2019 WEB-DL 720p", "c" * 40, int(3.0 * GB), 25, "Knaben"],
            ],
        ),
    ]
    pools = {
        str(record["query"]).casefold(): replay.poolreplay.batches_of(record) for record in records
    }
    item = replay.widen(
        "восхождение",
        pools,
        tune(Config(), CAUTIOUS),
        CAUTIOUS,
        lambda *_a, **_k: Origin(),
    )

    assert item.worth and item.alt == "The Climbers" and not item.missed
    assert not item.taken, "чужая картина под видом добора - это отказ, а не прибавка"
    assert any("brought a different picture" in note for note in item.notes), (
        "отказ не назван своим гейтом"
    )
    assert item.counts["строк после"] > item.counts["строк до"], "привезённое не сосчитано"


def geass_pools() -> list[dict[str, Any]]:
    """Тощая русская выдача первого сезона и латинский добор: он же и датированный спин-офф."""
    return [
        pool(
            "код гиас s1e1",
            RuTor=[
                [
                    "Код Гиас: Восставший Лелуш / Code Geass: Lelouch of the Rebellion "
                    "(2006) BDRip-HEVC 1080p",
                    "a" * 40,
                    int(8.2 * GB),
                    2,
                    "RuTor",
                ]
            ],
        ),
        pool(
            "Code Geass",
            Knaben=[
                [
                    "Code Geass: Lelouch of the Rebellion S01 [1-25] BDRip 1080p x264",
                    "b" * 40,
                    int(7.4 * GB),
                    60,
                    "Knaben",
                ],
                [
                    "Code Geass: Dakkan no Roze S01 [2024] WEB-DL 1080p",
                    "c" * 40,
                    int(5.0 * GB),
                    40,
                    "Knaben",
                ],
            ],
        ),
    ]


def test_щуп_привязки_мерит_оба_круга_и_сходится_со_щупом_добора() -> None:
    """Первый сезон сведён в ОДНУ картину и играет вместо спин-оффа.

    Добор привозит спрошенный первый сезон без года и датированный спин-офф 2024-го;
    гейт счёта картин этот добор отвергает, и щуп мерит контрфакт.

    🔴 TC-854. Русская раздача 2006 года сезона в имени не несёт, и раньше разбор звал
    её фильмом: картина разъезжалась надвое - бесстрочный сериал на 60 сид и датированный
    «фильм» на 2, - а честная строка извинялась за пропуск словами «спросили серию, а это
    другой тип». Вид, взятый у соседки по той же выдаче
    (:func:`~torrcast.domain.sibling_kind.sibling_kind`), сводит половины в одну картину:
    канонические имя и год, оба релиза в очереди, лучший по сидам первым. Извиняться
    стало не за что, и строка молчит. Сверка со щупом добора (``mismatches``) пуста:
    иначе замер снят не с того показа.
    """
    meter = probe("anchorprobe")
    records = geass_pools()
    pools = {
        str(record["query"]).casefold(): meter.poolreplay.batches_of(record) for record in records
    }
    canon = {
        "query": "код гиас s1e1",
        "short": "код гиас",
        "canon": "Код Гиас: Восставший Лелуш",
        "kind": "tv",
        "year": 2006,
    }
    rows, mismatches, _beyond = meter.circles(
        "код гиас s1e1",
        records[0],
        pools,
        tune(Config(), CAUTIOUS),
        CAUTIOUS,
        lambda *_a, **_k: Origin(title="Code Geass", year=2006, name="Код Гиас: Восставший Лелуш"),
        canon,
    )

    assert not mismatches, f"счёт со щупом добора не сошёлся: {mismatches}"
    by_scope = {row.scope: row for row in rows}
    widened = by_scope["добор"]
    assert widened.played == ["Код Гиас: Восставший Лелуш", 2006, "tv"], (
        "по Enter обязан идти спрошенный первый сезон, а не датированный спин-офф"
    )
    assert widened.verdict == meter.SAME
    # Привязка тут больше не нужна: год у картины СВОЙ, а не занятый у соседки.
    assert widened.anchor is None
    assert widened.guards["default_note"] == "", "сводить половины молча: объяснять нечего"


def dead_swarm_pool() -> dict[str, Any]:
    """Спрошенный сезон одной раздачей HEVC с дубляжом и живее его - тёзка другого года.

    Предмет замера: русская половина картины несёт единственный носитель серии, и
    носитель этот HEVC. Осторожный профиль его копией не играет, годным кандидатом он не
    становится, вес картины падает в ноль - и дефолт достаётся соседу под ТЕМ ЖЕ именем.
    """
    return pool(
        "код гиас s1e1",
        RuTor=[
            [
                "Код Гиас: Восставший Лелуш / Code Geass: Lelouch of the Rebellion R1 "
                "[01-25 из 25] (2006-2007) BDRip-HEVC 1080p-AniLibria",
                "a" * 40,
                int(6.3 * GB),
                7,
                "RuTor",
            ],
            [
                "Код Гиас: Восставший Лелуш / Gekijou Soushuuhen Code Geass: Hangyaku no "
                "Lelouch [Movie] [E1 of 3] [JAP+Sub] [2017, приключения, фантастика, меха, "
                "драма, BDRip] [720p]",
                "b" * 40,
                int(1.4 * GB),
                4,
                "RuTor",
            ],
        ],
    )


GEASS_CANON = {
    "query": "код гиас s1e1",
    "short": "код гиас",
    "canon": "Код Гиас: Восставший Лелуш",
    "kind": "tv",
    "year": 2006,
}


def swarm_case(profile: Any) -> Any:
    """Первый круг предметного пула глазами щупа роя на названном профиле."""
    meter = probe("swarmprobe")
    record = dead_swarm_pool()
    pools = {str(record["query"]).casefold(): meter.poolreplay.batches_of(record)}
    circles, mismatches, _beyond = meter.anchorprobe.menus_of(
        "код гиас s1e1", record, pools, tune(Config(), profile), profile, lambda *_a, **_k: Origin()
    )
    assert not mismatches, f"счёт со щупом добора не сошёлся: {mismatches}"
    return meter, meter.case_of("код гиас s1e1", circles[0], GEASS_CANON)


def test_щуп_роя_видит_мёртвую_свою_картину_и_разводит_её_с_чужим_сезоном() -> None:
    """Осторожный профиль: своя картина в меню есть, рой её ноль, Enter уехал к тёзке.

    Проверяется и разводка внутри класса: взятая картина носит ТО ЖЕ имя каталога, то
    есть это чужой сезон, а не чужая вещь, - и русская озвучка при подмене теряется.
    """
    meter, case = swarm_case(CAUTIOUS)

    assert case.verdict == meter.DEAD, f"класс определён неверно: {case.verdict}"
    assert case.mine == ["Код Гиас: Восставший Лелуш", 2006, "tv"]
    assert case.mine_alive == 0, "рой считается по ГОДНЫМ раздачам, а HEVC тут не годен"
    assert case.mine_ranked == 1, "в очередь отбора носитель серии всё-таки попал"
    assert case.mine_top == 7, "потолок ожидания - живые сиды самой раздачи, а не ноль"
    assert case.played == ["Код Гиас: Восставший Лелуш", 2017, "tv"]
    assert case.played_alive == 4, "взятый сосед сам ниже порога: он лишь наименее мёртвый"
    assert case.kin, "тёзка того же имени - чужой сезон, худший вид подмены"
    assert case.mine_dubbed and not case.played_dubbed, "подмена уносит русскую озвучку"
    numbers = meter.prices([case])
    assert numbers[meter.KIN] == 1 and numbers[meter.STRANGER] == 0
    assert numbers["взятая жива"] == 0 and numbers["теряется озвучка"] == 1
    assert numbers["своя годна, но тиха"] == 1 and numbers["ждать есть чего"] == 1


def test_щуп_роя_зеленеет_на_приставке_тем_же_пулом() -> None:
    """Отрицательная проба: порог роя - свойство ПРОФИЛЯ, и числа не переносятся.

    Пул тот же до строки. Приставка играет HEVC копией, тот же носитель становится
    годным кандидатом, вес картины поднимается до семи - и по Enter идёт спрошенный
    сезон. Щуп, красный на обоих профилях, мерил бы не рой, а что-то своё.
    """
    meter, case = swarm_case(ANDROID_TV)

    assert case.verdict == meter.SAME, f"на приставке предмета быть не должно: {case.verdict}"
    assert case.mine_alive == 7 and case.played == ["Код Гиас: Восставший Лелуш", 2006, "tv"]
    assert not meter.dead_rows([case], "первый"), "класс на этом профиле пуст"


def test_щуп_роя_не_считает_вторую_половину_подменой() -> None:
    """Половина той же картины - не предмет карточки, и в его число попадать не вправе.

    Сверка признаёт спрошенными обе половины: личность у них одна, подмены нет. Считать
    их «рой мёртв» значило бы раздуть число класса ровно там, где зритель получил ту
    самую картину. Потеря русского голоса на этой развилке при этом обязана остаться
    видимой - своим классом, а не молчанием.
    """
    meter = probe("swarmprobe")
    half = meter.Case(
        query="arcane s1e3",
        scope="первый",
        verdict=meter.HALF,
        mine=["Аркейн", 2021, "tv"],
        mine_alive=77,
        mine_dubbed=True,
        played=["Arcane", 2021, "tv"],
        played_alive=28,
    )
    dead = meter.Case(
        query="код гиас s1e1",
        scope="первый",
        verdict=meter.DEAD,
        mine=["Код Гиас: Восставший Лелуш", 2006, "tv"],
        mine_top=7,
        mine_dubbed=True,
        played=["Код Гиас: Восставший Лелуш", 2017, "tv"],
        played_alive=4,
        kin=True,
    )
    counted = meter.tally([half, dead], "первый")

    assert counted[meter.HALF] == 1 and counted[meter.DEAD] == 1
    assert [row.query for row in meter.dead_rows([half, dead], "первый")] == ["код гиас s1e1"]
    assert meter.prices([half])["теряется озвучка"] == 1, "потеря голоса обязана считаться"


def test_щуп_привязки_судит_бесстрочную_только_привязкой() -> None:
    """Без привязки бесстрочная не судится вовсе: имена у половин общие, счёт бы врал."""
    meter = probe("anchorprobe")
    canon = {"kind": "tv", "year": 2006}
    latin = Picture(title="Code Geass: Lelouch of the Rebellion", year=None, kind="tv")

    assert meter.verdict_of(latin, canon) == meter.UNSURE
    latin.anchor = 2006
    assert meter.verdict_of(latin, canon) == meter.SAME
    latin.anchor = 2024
    assert meter.verdict_of(latin, canon) == meter.UNSURE
    assert meter.verdict_of(None, canon) == meter.NONE
    assert meter.verdict_of(latin, None) == meter.UNMARKED
    dated = Picture(title="Код Гиас: Восставший Лелуш", year=2006, kind="tv")
    assert meter.verdict_of(dated, canon) == meter.SAME
    other = Picture(title="Код Гиас", year=2006, kind="movie")
    assert meter.verdict_of(other, canon) == meter.OTHER
    assert meter.verdict_of(Picture(title="Спин-офф", year=2024, kind="tv"), canon) == meter.OTHER


def test_щуп_привязки_краснеет_на_пришедшей_подмене() -> None:
    """Отрицательная проба счёта: подмена, которую привязка ПРИВЕСЛА, видна числом.

    Требование выкатки - «подмен пришло = 0»; щуп, не умеющий показать единицу на
    заведомой подмене, этот ноль не доказывает.
    """
    meter = probe("anchorprobe")
    base = [
        meter.Scope(
            query="q", scope="добор", played=["А", 2006, "tv"], dubbed=True, verdict=meter.SAME
        )
    ]
    rows = [
        meter.Scope(
            query="q", scope="добор", played=["Б", 2024, "tv"], dubbed=False, verdict=meter.OTHER
        )
    ]
    numbers = meter.diff(base, rows)["добор"]

    assert numbers["сменилось"] == 1
    assert numbers["ПОДМЕН ПРИШЛО"] == 1 and numbers["подмен ушло"] == 0
    assert numbers["пропала озвучка"] == 1, "потеря русского голоса тоже обязана краснеть"


def movie_pool() -> dict[str, Any]:
    """Выдача одного фильма: имена молчат и про сборник, и про серии."""
    return pool(
        "матрица",
        RuTor=[
            ["Матрица / The Matrix (1999) BDRip 1080p", "e" * 40, int(9.0 * GB), 70, "RuTor"],
            ["Матрица / The Matrix (1999) WEB-DL 720p", "f" * 40, int(3.0 * GB), 30, "RuTor"],
        ],
    )


def test_щуп_пака_отделяет_картину_без_очереди_серий() -> None:
    """Предмет замера - дефолт БЕЗ очереди: только там файл выбирается крупнейшим.

    Щуп обязан развести два случая, которые иначе сливаются в один: у сериала очередь
    серий есть и крупнейший файл никого не выбирает, у фильма её нет по построению
    (:func:`~torrcast.usecases.reinforce.plan_for.plan_for`) - и вот он и есть население
    болезни. Пока щуп считал бы оба, число замера было бы про весь корпус, а не про место.
    """
    packs = probe("packprobe")
    config = tune(Config(), CAUTIOUS)

    films = packs.picks([packs.replay(*_replayed(packs, movie_pool()), config, CAUTIOUS)])
    assert len(films) == 1, "дефолт фильма до щупа не доехал"
    assert films[0].picture.kind == "movie"
    assert not films[0].queued and films[0].at_risk, "фильм обязан попасть в население замера"
    assert films[0].by_name == "", "имя этой раздачи про пак молчит - выдумывать признак нечем"

    tv_pool = pool(
        "во все тяжкие s1e1",
        RuTor=[
            [
                "Во все тяжкие / Breaking Bad [S01] (2008) BDRip 1080p",
                "2" * 40,
                int(20.0 * GB),
                90,
                "RuTor",
            ]
        ],
    )
    series = packs.picks([packs.replay(*_replayed(packs, tv_pool), config, CAUTIOUS)])
    assert len(series) == 1 and series[0].picture.kind == "tv"
    assert series[0].queued and not series[0].at_risk, "у сериала очередь есть, крупнейший не судит"


def _replayed(packs: ModuleType, record: dict[str, Any]) -> tuple[str, list[list[Any]]]:
    return (str(record["query"]), packs.batches_of(record))


def test_щуп_пака_называет_сборник_по_имени() -> None:
    """Имя, которое само говорит «коллекция», щуп обязан назвать - иначе мерка слепа вся."""
    packs = probe("packprobe")
    collection = pool(
        "властелин колец",
        RuTor=[
            [
                "Властелин колец / The Lord of the Rings: Кинотрилогия (2001-2003) BDRip 1080p",
                "1" * 40,
                int(30.0 * GB),
                80,
                "RuTor",
            ]
        ],
    )
    found = packs.picks(
        [packs.replay(*_replayed(packs, collection), tune(Config(), CAUTIOUS), CAUTIOUS)]
    )
    assert found and found[0].by_name == "коллекция", "признак коллекции разбора потерян"


def test_доля_крупнейшего_файла_отличает_пак_от_одиночной_картины() -> None:
    """Правда о паке - в долях байтов, и мерить её надо по видеофайлам, а не по всем.

    🔴 Ровно эта доля и есть то, что достаётся зрителю: показ берёт КРУПНЕЙШИЙ видеофайл
    (:func:`~torrcast.adapters.stream_probe.pick_video_file.pick_video_file`). У картины с
    дорожкой и субтитрами рядом доля почти единица, у дюжины короткометражек - около доли
    одной части, и путать их нельзя. Звуковая дорожка на полгигабайта в счёт не идёт:
    считанная как видео, она занизила бы долю у здоровой раздачи и придумала бы пак.
    """
    packs = probe("packprobe")

    single = [["Матрица.mkv", 7 * GB], ["Ukrainian.ac3", GB // 2], ["cover.jpg", 40000]]
    count, share = packs.video_shares(single)
    assert count == 1 and share == 1.0, "у одиночной картины доля крупнейшего обязана быть единицей"

    shorts = [[f"Сборник/{n:02d} короткометражка.mkv", GB] for n in range(12)]
    count, share = packs.video_shares(shorts)
    assert count == 12 and abs(share - 1 / 12) < 1e-9, "доля части сборника посчитана не по видео"

    empty = packs.video_shares([["readme.txt", 10]])
    assert empty == (0, 0.0), "раздача без видео - это не пак, а ноль"


def test_щуп_пака_видит_сборник_ниже_дефолта() -> None:
    """Дефолт - не вся очередь: показ падает вниз по ней, когда рой молчит.

    🔴 Замер одного дефолта отвечает на вопрос про ПЕРВУЮ строку очереди и молчит про
    остальные, а играет в итоге та, до которой дошли. Ранжир сборник не выбрасывает, он
    уводит его ВНИЗ - значит на молчащих роях сборник и становится тем, что играет.
    Номер в очереди щуп обязан назвать: цена случая целиком в нём.
    """
    packs = probe("packprobe")
    record = pool(
        "властелин колец",
        RuTor=[
            [
                "Властелин колец / The Lord of the Rings (2001) BDRip 1080p",
                "3" * 40,
                int(12.0 * GB),
                90,
                "RuTor",
            ],
            [
                "Властелин колец / The Lord of the Rings: Кинотрилогия (2001-2003) BDRip 1080p",
                "4" * 40,
                int(30.0 * GB),
                50,
                "RuTor",
            ],
        ],
    )
    found = packs.picks(
        [packs.replay(*_replayed(packs, record), tune(Config(), CAUTIOUS), CAUTIOUS)]
    )
    assert found and found[0].by_name == "", "дефолтом стал сборник - ранжир сломан"
    assert found[0].pack_below == 2, "сборник вторым номером очереди не назван"

    # Снимать файлы надо у обоих: у дефолта и у сборника под ним, иначе «паков нет»
    # остаётся правдой про одну строку и молчанием про ту, что играет на молчащем рое.
    labels = [label for label, _ in packs.wanted(found)]
    assert labels == ["властелин колец", "властелин колец #2"], "сборник не попал в съём файлов"


def test_щуп_пака_не_числит_сборником_одиночную_очередь() -> None:
    """Очередь без сборника обязана давать ноль, иначе номер ниже дефолта - выдумка."""
    packs = probe("packprobe")
    found = packs.picks(
        [packs.replay(*_replayed(packs, movie_pool()), tune(Config(), CAUTIOUS), CAUTIOUS)]
    )
    assert found and found[0].pack_below == 0, "сборник найден там, где его нет"
    assert [label for label, _ in packs.wanted(found)] == ["матрица"]


def kind_corpus(tmp_path: Path) -> tuple[Path, Path]:
    """Маленький корпус и его разметка: фильм, сериал с меткой и сериал без меток."""
    corpus = tmp_path / "names.txt"
    corpus.write_text(
        "\n".join(
            [
                "Кино / Movie (1999) BDRip 1080p",
                "Сериал / Series S01 1080p",
                "Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO",
            ]
        ),
        encoding="utf-8",
    )
    marks = tmp_path / "marks.tsv"
    marks.write_text(
        "# комментарий\n"
        "Кино / Movie (1999) BDRip 1080p\tmovie\n"
        "Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO\ttv\tпак\n",
        encoding="utf-8",
    )
    return corpus, marks


def test_щуп_вида_считает_молчаливый_дефолт_по_разметке(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Вид «фильм» - это молчание разбора, и цену молчания называет разметка."""
    meter = probe("kindprobe")
    corpus, marks = kind_corpus(tmp_path)
    out = tmp_path / "kind.jsonl"

    assert meter.main(["--corpus", str(corpus), "--marks", str(marks), "--jsonl", str(out)]) == 0
    said = capsys.readouterr().out

    assert "поставлен молчанием (серийных меток нет): 2" in said
    assert "покрыто разметкой: 2 из 2" in said
    assert "неверно названы фильмом: 1 сериалов (паков 1, одиночных серий 0)" in said
    assert "Врата Штейна" in said, "неверно названный сериал обязан быть назван по имени"
    card = written(out)
    assert card["tool"] == "kindprobe"


def test_щуп_вида_не_считает_по_неполной_разметке(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Имя класса без ряда разметки - это исключение, а не сноска под таблицей."""
    meter = probe("kindprobe")
    corpus, marks = kind_corpus(tmp_path)
    marks.write_text(marks.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")

    assert meter.main(["--corpus", str(corpus), "--marks", str(marks)]) == 1
    assert "СЧЁТ НЕ СОШЁЛСЯ" in capsys.readouterr().err

    # И зеркально: ряд разметки про имя вне корпуса - та же недопустимость.
    corpus, marks = kind_corpus(tmp_path)
    with marks.open("a", encoding="utf-8") as handle:
        handle.write("Нет такого имени (1900)\ttv\tпак\n")
    assert meter.main(["--corpus", str(corpus), "--marks", str(marks)]) == 1


def test_щуп_вида_краснеет_на_пришедшей_подмене() -> None:
    """Отрицательная проба счёта: смена вида на неверный видна числом, а не молчанием.

    Требование выкатки - «подмен пришло = 0»; щуп, не умеющий показать единицу на
    заведомой подмене, этот ноль не доказывает. Рядом - и потеря озвучки.
    """
    meter = probe("kindprobe")
    base = [
        meter.Row(raw_name="а", kind="movie", voices=["Дубляж"], truth="movie", form=""),
        meter.Row(raw_name="б", kind="movie", voices=[], truth="tv", form="пак"),
    ]
    rows = [
        meter.Row(raw_name="а", kind="tv", voices=[], truth="movie", form=""),
        meter.Row(raw_name="б", kind="tv", voices=[], truth="tv", form="пак"),
    ]
    numbers = meter.diff(base, rows)

    assert numbers["сменилось"] == 2
    assert numbers["ПОДМЕН ПРИШЛО"] == 1 and numbers["подмен ушло"] == 1
    assert numbers["пропала озвучка"] == 1, "потеря русского голоса тоже обязана краснеть"


def season_circle(meter: ModuleType, plans: list[Any]) -> Any:
    """Круг одного запроса для щупа сезона: меню тут и есть предмет, каталог не нужен."""
    args = Args(query=["моб", "психо", "100", "s1e1"])
    return meter.anchorprobe.Circle(
        scope="первый", plans=plans, menu=[], catalog=[], args=args, asked="моб психо 100"
    )


def test_щуп_сезона_видит_чужую_часть_при_молчащей_о_сезоне_раздаче() -> None:
    """🔴 Предмет карточки: спрошен первый сезон, а по Enter идёт картина части 2.

    Имя раздачи о сезоне молчит, значит сезон файлам раздадут первым - и зритель получит
    вторую часть под именем первой. Честная строка выбора при этом обязана быть приложена
    к случаю: без неё подмена уезжает молча, а это худший её вид.
    """
    meter = probe("seasonprobe")
    plans = [
        world.plan("Mob Psycho 100", 2018, kind="movie", asked_series=True),
        world.plan(
            "Mob Psycho 100 2",
            None,
            kind="tv",
            part=2,
            season=1,
            asked_series=True,
            pool=[world.film("Mob Psycho 100 2 - AniLiberty [WEBRip 720p][AVC][1-13]", kind="tv")],
        ),
    ]
    case = meter.case_of("моб психо 100 s1e1", season_circle(meter, plans))

    assert case.verdict == meter.OTHER, f"класс определён неверно: {case.verdict}"
    assert case.asked == "s1e1" and case.part == 2
    assert not case.named, "имя раздачи о сезоне молчит - назвать его щуп не вправе"
    assert not case.blind, "часть названа каталогом, слепым такой случай не бывает"
    assert case.note, "к подмене обязана быть приложена честная строка выбора"


def test_щуп_сезона_не_считает_подменой_пак_названного_сезона() -> None:
    """Отрицательная проба: пак ``[S01-06]`` на просьбу ``s1e1`` - верная раздача.

    Очередь отбора уже отсеяна по покрытию серии, и раздача, НАЗВАВШАЯ сезоны, называет
    среди них спрошенный. Красней щуп и тут - его ноль подмен не стоил бы ничего: он
    краснел бы на всяком многосезонном паке, то есть мерил бы не подмену.
    """
    meter = probe("seasonprobe")
    pack = replace(
        world.film("Острые козырьки / Peaky Blinders [S01-06] BDRip 1080p", kind="tv"),
        seasons=(1, 2, 3, 4, 5, 6),
    )
    plans = [
        world.plan("Острые козырьки", 2013, kind="tv", season=1, asked_series=True, pool=[pack])
    ]
    case = meter.case_of("острые козырьки s1e1", season_circle(meter, plans))

    assert case.verdict == meter.SAME, f"класс определён неверно: {case.verdict}"
    assert case.named == [1, 2, 3, 4, 5, 6] and not case.blind


def test_щуп_сезона_называет_слепым_случай_без_единой_подписи() -> None:
    """Молчат оба звена - случай щупу невидим, и молчать об этом он не вправе.

    Ноль подмен на корпусе, где половина случаев слепа, читался бы как ноль беды. Поэтому
    слепые считаются своим числом рядом с подменами, а не растворяются в классе «тот».
    """
    meter = probe("seasonprobe")
    plans = [
        world.plan(
            "Ход королевы",
            2020,
            kind="tv",
            season=1,
            asked_series=True,
            pool=[world.film("Ход королевы 2020 WEB-DL 1080p", kind="tv")],
        )
    ]
    case = meter.case_of("ход королевы s1e1", season_circle(meter, plans))

    assert case.verdict == meter.SAME and case.blind, "ни часть, ни сезон не названы"


def test_щуп_сезона_краснеет_на_пришедшей_подмене() -> None:
    """Отрицательная проба счёта: требование выкатки - «подмен пришло = 0».

    Щуп, не умеющий показать единицу на заведомой подмене, этого нуля не доказывает.
    """
    meter = probe("seasonprobe")
    base = [
        meter.Case(query="а", scope="первый", verdict=meter.SAME, played=["А", 2016, "tv"]),
        meter.Case(query="б", scope="первый", verdict=meter.OTHER, played=["Б 2", None, "tv"]),
    ]
    rows = [
        meter.Case(query="а", scope="первый", verdict=meter.OTHER, played=["А 2", None, "tv"]),
        meter.Case(query="б", scope="первый", verdict=meter.SAME, played=["Б", 2016, "tv"]),
    ]
    numbers = meter.diff(base, rows)

    assert numbers["сменилось приговоров"] == 2
    assert numbers["подмен ПРИШЛО"] == 1 and numbers["подмен ушло"] == 1
    assert numbers["молчаливых подмен"] == 1, "подмена без честной строки обязана краснеть"


#: Начало выдуманного окна замера: метки журнала - настоящие секунды эпохи, и короче
#: девяти знаков они не бывают (:data:`tvjournal.STAMP`).
WINDOW = 1787900000.0


def _journal(began: float, marks: list[float], noise: int = 0) -> bytes:
    """Журнал приёмника из готовых меток: столько строк, сколько названо."""
    lines = [b"--------- beginning of main"] * noise
    lines += [f"{began + mark:.3f}   485   485 I adbd    : строка".encode() for mark in marks]
    return b"\n".join(lines) + b"\n"


def test_журнал_без_меток_это_брак_а_не_ноль_голоданий() -> None:
    """Нечитанный прибор - брак замера, а не спокойный показ.

    🔴 TC-867. «В журнале нет строки» не значит «события не было»: у молчащего прибора
    ноль голоданий и у чистого показа ноль голоданий выглядят совершенно одинаково.
    """
    told = probe("tvjournal").life(WINDOW, WINDOW + 400.0, b"")

    assert not told.fit
    assert "не читан" in told.why


def test_плотный_журнал_живший_миг_это_брак() -> None:
    """Живость журнала меряется ОКНОМ, а не строками: залп в первый миг живостью не был.

    🔴 TC-867. Прежний признак - «строк не меньше пятисот» - засчитывал ровно такие
    прогоны: журнал вываливал тысячи строк кольцевого буфера за первую секунду, умирал,
    и все четыреста секунд замера приёмник никто не читал. Пять прогонов архива прошли
    этот признак с 1163-4335 строками при живом журнале от одной до двадцати шести секунд.
    """
    journal = probe("tvjournal")
    marks = [index * 0.0002 for index in range(5000)]

    told = journal.life(WINDOW, WINDOW + 400.0, _journal(WINDOW, marks))

    assert told.lines >= 500, "строк тут заведомо больше прежнего порога"
    assert not told.fit
    assert "ослеп посреди" in told.why


def test_журнал_кольцевого_буфера_это_брак() -> None:
    """Журнал, начатый ДО прогона, несёт чужое окно - и назван браком отдельно.

    🔴 TC-867. Ровно так выглядел единственный прогон архива, считавшийся образцовым:
    4335 строк, шесть минут плотного журнала - и все они сняты до начала замера, потому
    что кольцевой буфер не был очищен, а поток умер через секунду после старта.
    """
    journal = probe("tvjournal")
    # Как у R1: шесть минут буфера до начала замера и одна секунда внутри него.
    marks = [-378.6 + index * 0.1 for index in range(3796)]

    told = journal.life(WINDOW, WINDOW + 400.0, _journal(WINDOW, marks))

    assert not told.fit
    assert told.backlog > 300.0
    assert "кольцевой буфер" in told.why


def test_журнал_покрывший_окно_годен() -> None:
    """Годен тот журнал, который не молчал дольше порога ни разу за всё окно."""
    journal = probe("tvjournal")
    marks = [index * 5.0 for index in range(81)]

    told = journal.life(WINDOW, WINDOW + 400.0, _journal(WINDOW, marks))

    assert told.fit, told.why
    assert told.silence <= journal.SILENCE


def test_щуп_журнала_молчит_о_голоданиях_на_мёртвом_приборе(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Признак обязан ТРЕБОВАТЬ вторую половину меры, а не затыкать её нулём.

    🔴 TC-867. Счёт голоданий на оборванном журнале - это ноль, купленный мёртвым
    прибором, и уезжает он в отчёт неотличимо от заработанного. Поэтому на браке щуп не
    печатает счёт вовсе и возвращает не ноль.
    """
    journal = probe("tvjournal")
    out = tmp_path / "logcat.txt"

    def torn(_device: str, where: Path, _seconds: float) -> object:
        where.write_bytes(_journal(WINDOW, [index * 0.001 for index in range(2000)]))
        return journal.Held(1, WINDOW, WINDOW + 400.0)

    def whole(_device: str, where: Path, _seconds: float) -> object:
        where.write_bytes(_journal(WINDOW, [index * 5.0 for index in range(81)]))
        return journal.Held(9, WINDOW, WINDOW + 400.0)

    monkeypatch.setattr(
        sys, "argv", ["tvjournal.py", "10.0.0.5:5555", "--seconds", "400", "--out", str(out)]
    )
    assert journal.main(follow=torn) == 1
    torn_said = capsys.readouterr()
    assert "БРАК ЗАМЕРА" in torn_said.err
    assert "DEMUXER_UNDERFLOW" not in torn_said.out, "счёт на мёртвом приборе назван вслух"

    assert journal.main(follow=whole) == 0
    whole_said = capsys.readouterr()
    assert "ГОДЕН" in whole_said.out
    assert "DEMUXER_UNDERFLOW за прогон: 0" in whole_said.out


def test_порог_тишины_журнала_лежит_между_живым_и_ослепшим() -> None:
    """Порог живости обоснован РАЗБРОСОМ замеров, а не выбран с потолка.

    🔴 TC-867. Порог обязан лежать выше худшей тишины живого журнала (иначе он бракует
    годные прогоны) и ниже самой короткой тишины ослепшего (иначе пропускает слепоту).
    Оба края - замеры, и оба названы числами в самом щупе; проверка держит порог внутри.

    Прежний признак «строк не меньше пятисот» ни одного из этих краёв не имел вовсе.
    """
    journal = probe("tvjournal")

    assert journal.SILENCE_LIVE < journal.SILENCE < journal.SILENCE_BLIND, (
        f"порог {journal.SILENCE} вне замеренного промежутка "
        f"({journal.SILENCE_LIVE}, {journal.SILENCE_BLIND})"
    )
    # Живой край проверяется тем же признаком: тишина ровно в замеренную живую годна.
    marks = [0.0, journal.SILENCE_LIVE, 2 * journal.SILENCE_LIVE]
    assert journal.life(WINDOW, WINDOW + 2 * journal.SILENCE_LIVE, _journal(WINDOW, marks)).fit
    # Ослепший край - тоже: самая тесная замеренная слепота обязана быть браком.
    assert not journal.life(WINDOW, WINDOW + journal.SILENCE_BLIND, _journal(WINDOW, [0.0])).fit
