"""Зеркало перекладки точечных кусков прежнего способа."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, vault, world
from torrcast.usecases.warm.relay import relay
from torrcast.usecases.warm.settings import META

if TYPE_CHECKING:
    from pathlib import Path


def test_only_spots_laid_the_previous_way_are_rejected(tmp_path: Path) -> None:
    """Переиспользуемые копии остаются, а старые точечные куски уходят вместе с метками."""
    world()
    store = vault(tmp_path)
    for slot in range(3):
        lay(store, slot)
    store.served.mark(1)
    (store.dir / META).write_text(json.dumps({"key": store.key, "at": 1.0}), encoding="utf-8")

    assert relay(store) == (1,)
    assert store.slots() == {0, 2} and 1 not in store.served
