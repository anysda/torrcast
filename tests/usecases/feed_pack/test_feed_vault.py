"""Договор хранилища прогретого в том объёме, в каком его знает лента показа."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import vault
from torrcast.usecases.feed_pack.feed_vault import _Vault

if TYPE_CHECKING:
    from pathlib import Path


def test_the_feed_asks_the_vault_for_names_and_nothing_more(tmp_path: Path) -> None:
    """Показу от прогрева нужны имена файлов, а не бюджет диска и не вытеснение.

    Договор снят с настоящих вопросов ленты: полный
    :class:`torrcast.usecases.warm.vault.Vault` сюда не приходит, и стендовое хранилище
    подходит ленте целиком. Промах в договоре виден проверкой типов на этой строке, а не
    посреди зелёного прогона.
    """
    kept: _Vault = vault(tmp_path)

    assert kept.path(3).name == "v3.ts" and kept.head().name == "init.mp4"

    kept.path(3).write_bytes(b"x")
    kept.reject(3)

    assert not kept.path(3).exists()
