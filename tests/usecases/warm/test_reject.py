"""Зеркало удаления забракованного куска из каталога и памяти раздачи."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, vault
from torrcast.usecases.warm.reject import reject

if TYPE_CHECKING:
    from pathlib import Path


def test_rejected_recode_disappears_from_disk_and_the_live_serving_memory(tmp_path: Path) -> None:
    """Два источника правды очищаются одним действием, иначе раздача врёт после перекладки."""
    store = vault(tmp_path)
    lay(store, 2)
    store.served.mark(2)

    reject(store, 2)

    assert not store.have(2) and not store.spot(2).exists()
    assert 2 not in store.served
