"""Проверяет черновик карты: своё имя каждому писателю, и лежит он рядом с картой."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from torrcast.adapters.stream_pack._keys_draft import _keys_draft


@pytest.mark.machine
def test_two_writers_of_one_map_do_not_share_a_draft(tmp_path: Path) -> None:
    """Черновик кэша - файл на писателя, а не на URL: иначе наружу уехала бы склейка.

    Замок на карту берётся не всегда (протух, каталог только для чтения), и два писателя
    на одно имя пишут вперемешку.
    """
    cache = tmp_path / "abcdef0123456789.json"
    drafts: list[Path] = []
    # ⚠️ Писатели обязаны быть живы ОДНОВРЕМЕННО: разойдись они по времени - и номер
    # потока переиспользуется, а вместе с ним и имя. Развести надо ровно тех, кто пишет
    # вперемешку, и барьер держит в пробе именно этот случай.
    gate = threading.Barrier(2)

    def draft() -> None:
        gate.wait(timeout=5)
        drafts.append(_keys_draft(cache))
        gate.wait(timeout=5)

    writers = [threading.Thread(target=draft) for _ in range(2)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join(timeout=10)

    assert len(set(drafts)) == 2, f"два писателя взяли одно имя: {drafts}"
    for name in [*drafts, _keys_draft(cache)]:
        assert name != cache and name.name.endswith(".tmp")
        assert name.parent == cache.parent, "черновик кладётся рядом: replace атомарен в одной fs"
