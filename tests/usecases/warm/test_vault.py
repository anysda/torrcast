"""Каталог прогретого и бюджет диска: что считается прогретым и кого вытесняют."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, vault, world
from torrcast.usecases.warm.settings import META
from torrcast.usecases.warm.vault import Vault, _size, _title, _touched, _weigh

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_piece_lives_under_its_own_name_in_its_own_catalogue(tmp_path: Path) -> None:
    """Имя куска - это его место в фильме, и каталог у показа свой по ключу."""
    store = vault(tmp_path, key="ключ")

    assert store.dir == tmp_path / "warm" / "ключ"
    assert store.path(7).name == "v7.ts"
    assert store.spot(7).name == "v7.rec", "метка перекода не должна попадать под v*.ts"
    assert not store.have(7)
    lay(store, 7)
    assert store.have(7)


def test_only_pieces_the_show_would_take_are_counted_with_a_cap(tmp_path: Path) -> None:
    """С потолком считаются только куски, которые показ и правда возьмёт с диска."""
    store = vault(tmp_path)
    lay(store, 0, size=100)
    lay(store, 1, size=1000)
    (store.dir / "мусор.txt").write_bytes(b"x" * 5000)

    assert store.slots() == {0, 1}, "прогреву видно всё, что лежит"
    assert store.slots(cap=500) == {0}, "тяжёлая копия зачлась запасом показа"
    assert store.size() == 1100, "вес каталога считает чужие файлы"


def test_opening_writes_a_passport_the_budget_reads_by(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Паспорт нужен бюджету: по его времени считается давность показа."""
    fake = world(monkeypatch)
    store = Vault(root=tmp_path / "warm", key="ключ", title="Кино")
    store.open()

    found = json.loads((store.dir / META).read_text(encoding="utf-8"))
    assert found == {"key": "ключ", "title": "Кино", "at": fake.stamp}
    assert _title(store.dir) == "Кино"
    assert _touched(store.dir) > 0.0


def test_the_budget_evicts_the_oldest_stranger_and_never_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Вытесняются чужие каталоги от самого давнего; свой и соседняя серия неприкосновенны."""
    fake = world(monkeypatch)
    mine = vault(tmp_path, key="моя", budget=3000)
    mine.keep = frozenset({"соседняя"})
    for key, stamp in (("старая", 1.0), ("свежая", 9.0)):
        other = vault(tmp_path, key=key)
        lay(other, 0, size=1000)
        (other.dir / META).write_text("{}", encoding="utf-8")
        os.utime(other.dir / META, (stamp, stamp))
    neighbour = vault(tmp_path, key="соседняя")
    lay(neighbour, 0, size=1000)

    assert mine.fit(1000) == "", "место под кусок не нашлось"
    assert not (tmp_path / "warm" / "старая").exists(), "самый давний чужой каталог остался"
    assert (tmp_path / "warm" / "соседняя" / "v0.ts").exists(), "соседнюю серию выели"
    assert [event for event, _args, _facts in fake.events] == ["evict"]
    assert fake.events[0][2]["freed"] == 1000, "вес сняли уже после сноса"


def test_a_budget_and_a_disk_are_two_different_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Наш бюджет и чужое место на разделе путать нельзя: причины разные."""
    world(monkeypatch)
    store = vault(tmp_path, budget=1000, floor=0)
    lay(store, 0, size=900)

    assert "бюджет диска" in store.fit(500), "упёртый бюджет назвался чем-то другим"

    roomy = vault(tmp_path, key="просторная", budget=1 << 40, floor=1 << 62)
    assert "последний запас" in roomy.fit(1), "запас раздела назвался бюджетом"


def test_clearing_hands_the_catalogue_to_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стирание идёт через среду: слой сценариев сам файлы не сносит."""
    fake = world(monkeypatch)
    store = vault(tmp_path)

    store.clear()

    assert fake.removed == [store.dir]


def test_an_unreadable_file_weighs_nothing_and_a_missing_passport_is_nameless(
    tmp_path: Path,
) -> None:
    """Ноль тут безопасен: кусок, пропавший между глобом и ``stat``, отдача переживает."""
    assert _size(tmp_path / "нет.ts") == 0
    assert _weigh(tmp_path / "нет") == 0
    assert _title(tmp_path / "нет") == ""
    assert _touched(tmp_path / "нет") == 0.0
