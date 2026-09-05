"""Зеркало :mod:`torrcast.usecases.warm.strip_forms`: место полок прежних форм ключа."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, world
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.warm._vault_disk import _weigh
from torrcast.usecases.warm.key_form import KEY_FORM
from torrcast.usecases.warm.settings import META
from torrcast.usecases.warm.vault import Vault

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _shelf(root: Path, key: str, weight: int, form: str, age: float) -> None:
    """Полка на диске: паспорт названной формы ключа и один кусок названного веса."""
    shelf = Vault(root=root, key=key, floor=0, form=form)
    shelf.open()
    lay(shelf, 0, size=weight)
    os.utime(shelf.dir / META, (time.time() - age, time.time() - age))


def _room(total: int) -> Callable[[Path], int]:
    """Раздел, на котором свободно ровно то, что не занято прогретым: снос полки обязан
    двигать замер, иначе вытеснение не остановится на первой же отданной полке."""
    return lambda where: total - _weigh(where)


def test_the_floor_gives_back_the_room_held_by_a_previous_key_form(tmp_path: Path) -> None:
    """Полку, обесцененную сменой ФОРМЫ ключа, отдаёт пол свободного места.

    Замер на стенде 05-09-2026: 10.7 ГБ прогретого прежней формой при 2.8 ГБ свободных, и
    прогрев вставал навсегда. Бюджет эти гигабайты не трогал (полка легче бюджета), а пол
    только отказывал, и сам себя показ из тупика не выводил.
    """
    sky = world()
    root = tmp_path / "warm"
    _shelf(root, "давняя-прежней-формы", 900, form="прежняя форма", age=3000.0)
    _shelf(root, "свежая-прежней-формы", 500, form="прежняя форма", age=100.0)
    # Самая давняя из всех: не будь форма записана в паспорт, ушла бы первой именно она.
    _shelf(root, "полка-этой-сборки", 400, form=KEY_FORM, age=5000.0)
    mine = Vault(root=root, key="мой", budget=1 << 62, floor=1000, free_of=_room(2500))
    mine.open()

    assert mine.fit(200) == "", "место осиротевшей полки так и не отдано"
    assert not (root / "давняя-прежней-формы").exists(), "самая давняя сирота не вытеснена"
    assert (root / "свежая-прежней-формы").exists(), "отдано больше, чем просили под запрос"
    assert (root / "полка-этой-сборки").exists(), "вытеснена полка, которую эта сборка найдёт"
    said = [facts for name, _, facts in sky.events if name == "evict"]
    assert [facts["key"] for facts in said] == ["давняя-прежней-формы"], (
        "в ленте не сказано, кого и на сколько освободили"
    )
    assert said[0]["freed"] == 900


def test_the_floor_never_takes_a_shelf_this_build_can_still_find(tmp_path: Path) -> None:
    """Отдаётся только то, что не найдётся больше ни по одному ключу этой сборки.

    Полка, заведённая этой же сборкой, не трогается даже тогда, когда она одна стоит
    между прогревом и местом: под ней может идти живой показ, и его прогретое дороже
    нашего прогрева. Соседнюю серию (:attr:`Vault.keep`) не трогаем тем более.
    """
    sky = world()
    root = tmp_path / "warm"
    _shelf(root, "чужой-живой-показ", 900, form=KEY_FORM, age=3000.0)
    _shelf(root, "соседняя-серия", 700, form="прежняя форма", age=4000.0)
    mine = Vault(
        root=root,
        key="мой",
        budget=1 << 62,
        floor=1000,
        keep=frozenset({"соседняя-серия"}),
        free_of=_room(2500),
    )
    mine.open()
    refusal = mine.fit(200)

    floor_head = phrase("warm.floor_reached", free="FREE-MARK").split("FREE-MARK")[0]
    assert floor_head in refusal, "отказ по полу свободного места не назван"
    assert (root / "чужой-живой-показ").exists(), "вытеснена полка живого показа этой сборки"
    assert (root / "соседняя-серия").exists(), "вытеснена соседняя серия того же показа"
    assert sky.removed == [], "под полом отдано то, что эта сборка ещё найдёт"
