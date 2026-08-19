"""Проверяет, что раздача просит у поставщика сегментов ровно то, что он умеет."""

from __future__ import annotations

from torrcast.adapters.http_server._feed import _Feed
from torrcast.usecases.feed_pack.feed import Feed


def _asked() -> set[str]:
    """Имена, которые договор раздачи требует от поставщика."""
    fields = set(getattr(_Feed, "__annotations__", {}))
    methods = {
        name for name, value in vars(_Feed).items() if not name.startswith("_") and callable(value)
    }
    return fields | methods


def test_the_serving_side_asks_for_the_manifest_the_segment_and_the_pack_directory() -> None:
    """Договор узкий намеренно: раздача не знает про упаковку ничего сверх этих трёх имён.

    ``out`` тут не украшение - по нему отданный кусок делится на «упаковано сейчас» и
    «взято с прогретого», и без этого в следе не видно, чей это был кусок.
    """
    assert _asked() == {"out", "manifest", "segment"}


def test_the_real_feed_supplies_everything_that_is_asked() -> None:
    """Настоящий поставщик отвечает договору: разъедься они - раздача упадёт на живом показе.

    Проверяется именно живой :class:`Feed`, а не заглушка: договор писан под него, и
    молчаливое переименование его метода никакой сухой тест больше не поймает.
    """
    missing = [name for name in _asked() if not hasattr(Feed, name)]
    assert not missing, f"поставщик сегментов не умеет: {missing}"
