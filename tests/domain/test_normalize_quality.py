"""Зеркало :mod:`torrcast.domain.normalize_quality`."""

from torrcast.domain.normalize_quality import _normalize_quality


def test_normalize_quality_is_exposed() -> None:
    assert _normalize_quality is not None
