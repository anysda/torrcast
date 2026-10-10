"""Зеркало :mod:`torrcast.usecases.warm.reclaim_floor`: тесный раздел отдаёт кэш."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, world
from torrcast.domain.catalogs.warm.en import en
from torrcast.domain.catalogs.warm.ru import ru
from torrcast.usecases.warm._vault_disk import _weigh
from torrcast.usecases.warm.key_form import KEY_FORM
from torrcast.usecases.warm.settings import META
from torrcast.usecases.warm.vault import Vault

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _shelf(root: Path, key: str, weight: int, age: float, *, form: str = KEY_FORM) -> None:
    """Настоящая полка с куском, паспортом, названием и названной давностью."""
    shelf = Vault(root=root, key=key, title=f"Показ {key}", floor=0, form=form)
    shelf.open()
    lay(shelf, 0, size=weight)
    stamp = time.time() - age
    os.utime(shelf.dir / META, (stamp, stamp))


def _room(capacity: int) -> Callable[[Path], int]:
    """Свободное место настоящего тесного склада через штатный порт замера диска."""
    return lambda where: capacity - _weigh(where)


def test_a_tight_floor_returns_current_shelves_to_raise_the_show(tmp_path: Path) -> None:
    """28.4 ГБ / 33 полки / 2.1 ГБ свободно в масштабе: свой кэш спасает показ."""
    sky = world()
    root = tmp_path / "warm"
    _shelf(root, "самая-давняя", 14, 5000.0)
    for number in range(31):
        _shelf(root, f"полка-{number:02}", 8, 4000.0 - number)
    _shelf(root, "крупная", 22, 100.0)
    store = Vault(root=root, key="новый", budget=300, floor=30, free_of=_room(305))

    assert _weigh(root) == 284 and store.free() == 21
    assert store.fit(5) == "", "место было в отдаваемом складе, а показ всё равно отказан"
    assert store.free() == 35
    said = [facts for event, _, facts in sky.events if event == "evict"]
    assert said == [
        {
            "key": "самая-давняя",
            "freed": 14,
            "need": 5,
            "title": "Показ самая-давняя",
        }
    ]


def test_the_floor_never_takes_the_current_or_neighbouring_show(tmp_path: Path) -> None:
    """Своя и соседняя полки остаются, даже если они давнее всех отдаваемых."""
    sky = world()
    root = tmp_path / "warm"
    _shelf(root, "мой", 10, 5000.0)
    _shelf(root, "соседний", 10, 4000.0)
    _shelf(root, "давний-свободный", 20, 3000.0)
    store = Vault(
        root=root,
        key="мой",
        keep=frozenset({"соседний"}),
        budget=100,
        floor=30,
        free_of=_room(55),
    )

    assert store.fit(5) == ""
    assert store.dir.exists() and (root / "соседний").exists()
    assert not (root / "давний-свободный").exists()
    assert [facts["key"] for event, _, facts in sky.events if event == "evict"] == [
        "давний-свободный"
    ]


def test_the_floor_refuses_in_words_when_only_live_shelves_remain(tmp_path: Path) -> None:
    """Отдать нечего: законный отказ прямо называет нехватку места на диске на обоих языках."""
    sky = world()
    root = tmp_path / "warm"
    _shelf(root, "мой", 20, 5000.0)
    _shelf(root, "соседний", 20, 4000.0)
    store = Vault(
        root=root,
        key="мой",
        keep=frozenset({"соседний"}),
        budget=100,
        floor=30,
        free_of=_room(45),
    )

    refusal = store.fit(5)

    assert (
        refusal
        == en()["warm.floor_reached"].format(free="0.0")
        == ("not enough disk space: the partition has 0.0 GB free - that's the last reserve")
    )
    assert ru()["warm.floor_reached"].format(free="0.0") == (
        "на диске не хватает места: на разделе свободно 0.0 ГБ - это последний запас"
    )
    assert sky.removed == []


def test_old_forms_and_current_shelves_make_room_in_their_oldest_order(tmp_path: Path) -> None:
    """Сначала прежние формы, затем нынешние; оба пути внутри идут от давней полки."""
    sky = world()
    root = tmp_path / "warm"
    _shelf(root, "давняя-прежняя", 10, 5000.0, form="прежняя")
    _shelf(root, "свежая-прежняя", 3, 4000.0, form="прежняя")
    _shelf(root, "давняя-текущая", 20, 3000.0)
    _shelf(root, "свежая-текущая", 20, 100.0)
    store = Vault(root=root, key="мой", budget=100, floor=20, free_of=_room(53))

    assert store.fit(5) == ""
    evicted = [facts["key"] for event, _, facts in sky.events if event == "evict"]
    assert evicted == ["давняя-прежняя", "свежая-прежняя", "давняя-текущая"]
    assert (root / "свежая-текущая").exists(), "отдано больше места, чем требовал пол"


def test_a_roomy_disk_evicts_nothing(tmp_path: Path) -> None:
    """Места хватает без отдачи: ни один из вытеснителей не запускается."""
    sky = world()
    root = tmp_path / "warm"
    _shelf(root, "давняя", 40, 5000.0)
    store = Vault(root=root, key="мой", budget=100, floor=20, free_of=_room(100))

    assert store.fit(5) == ""
    assert (root / "давняя").exists()
    assert sky.events == [] and sky.removed == []


def _found(root: Path) -> Path:
    """Каталог ``lost+found`` отдельного раздела под складом: без паспорта и с находкой."""
    found = root / "lost+found"
    found.mkdir(parents=True)
    (found / "#12").write_bytes(b"x" * 5)
    return found


def test_lost_and_found_of_the_partition_is_never_a_shelf(tmp_path: Path) -> None:
    """Живой стенд 10-10: склад на своём разделе, бюджет и пол сносили ``lost+found``.

    Ни бюджет, ни прежняя форма, ни пол не вправе считать его полкой: в ленте не должно
    быть ``evict lost+found``, а сносить system-owned каталог служба под root не смеет.
    """
    for budget, floor, capacity in ((15, 0, 1 << 30), (1000, 30, 40)):
        sky = world()
        root = tmp_path / f"warm-{budget}"
        found = _found(root)
        _shelf(root, "старая", 10, 3000.0)
        store = Vault(root=root, key="новый", budget=budget, floor=floor, free_of=_room(capacity))

        assert store.fit(8 if floor == 0 else 5) == ""
        assert (found / "#12").exists(), "снесён lost+found раздела"
        assert [facts["key"] for event, _, facts in sky.events if event == "evict"] == ["старая"]
        assert found not in sky.removed


def test_an_unreadable_lost_and_found_does_not_blind_the_floor(tmp_path: Path) -> None:
    """Живой стенд 10-10: в контейнере ``lost+found`` раздела - ``nobody`` 0700.

    Проверка паспорта внутри него падает отказом в доступе; склад обязан пропустить этот
    каталог, а не потерять из виду все полки и встать на полу при отдаваемой чужой.
    """
    sky = world()
    root = tmp_path / "warm"
    found = _found(root)
    _shelf(root, "1234567890abcdef", 10, 3000.0)
    store = Vault(root=root, key="новый", budget=1000, floor=30, free_of=_room(40))
    found.chmod(0)
    try:
        assert store.fit(5) == "", "полка была отдаваемой, а пол отказал"
    finally:
        found.chmod(0o700)
    evicted = [facts["key"] for event, _, facts in sky.events if event == "evict"]
    assert evicted == ["1234567890abcdef"]
    assert (found / "#12").exists()
