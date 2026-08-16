"""Зеркало :mod:`torrcast.domain.cluster`."""

from torrcast.domain.cluster import cluster


def test_cluster_is_exposed() -> None:
    assert cluster is not None
