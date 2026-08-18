"""Зеркально проверяет строку о запасе показа в кэше службы."""

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.usecases.cache_reserve import _cache_reserve


def test_a_release_without_an_owner_is_not_asked_about() -> None:
    assert _cache_reserve(Config(), Entry(title="Кино", magnet="magnet:?x=1")) == ""
