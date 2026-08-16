"""Зеркало :mod:`torrcast.ports.legacy_namespace`."""

from torrcast.ports.legacy_namespace import legacy_namespace


def test_legacy_namespace_collects_named_dependencies() -> None:
    assert legacy_namespace(torrcast__domain__version=("__version__",))["__version__"]
