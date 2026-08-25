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
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import torrcast
from torrcast.adapters.chromecast.profile_detector import ProfileDetector, detector
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
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
    assert "профиль приёмника: androidtv" in said and "по паспорту:" in said
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

    assert "профиль приёмника: q70d" in said and "назван руками" in said


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


def test_щуп_перемоток_берёт_удержание_и_потолок_у_профиля() -> None:
    """Удержание запроса и потолок веса куска - свойства приёмника, не щупа.

    🔴 Пока оба профиля были по 16 МБ, расхождение не проявлялось. Когда у приставки
    потолок веса куска стал 28 МБ, щуп строил сетку под 28 (профиль в ``layout`` он
    передавал честно), а раздачу собирал без ``cap`` - с осторожным умолчанием 16 МБ:
    на релизе, чьи копии тяжелее 16 МБ, ни один кусок не выкладывался, и здоровый
    продукт выглядел «ни кадра». Показ оба числа берёт у профиля
    (:func:`torrcast.usecases.playback._tract._tract`), щуп обязан мерить тот же тракт.
    """
    source = (SCRIPTS / "seekcheck.py").read_text(encoding="utf-8")
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Feed"
    ]
    assert len(calls) == 1, "щуп собирает ленту показа ровно раз"
    given = {kw.arg: ast.unparse(kw.value) for kw in calls[0].keywords}

    assert given.get("wait") == "choice.profile.hold_seconds"
    assert given.get("cap") == "choice.profile.max_segment_bytes"


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
    assert any("привёз больше картин" in note for note in item.notes)
    assert ask("нет такой картины") == Origin(), "без кэша справка молчит, а не выдумывает"
