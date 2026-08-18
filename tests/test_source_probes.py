"""Щупы источников не превращают отказ среды в убедительное число каталога."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def probe(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_catalog_probe_stops_before_querying_a_banned_source() -> None:
    catalog = probe("catalogprobe")
    calls: list[str] = []

    def answer(_base: str, _key: str, path: str, _timeout: float) -> Any:
        calls.append(path)
        if path == "/api/v1/indexer":
            return [{"id": 1, "name": "one", "enable": True}]
        if path == "/api/v1/indexerstatus":
            return [{"indexerId": 1, "disabledTill": "later"}]
        raise AssertionError("поиск поверх отсрочки начался")

    with pytest.raises(RuntimeError, match="замер остановлен"):
        catalog.measure("http://p", "key", "movie", 1, answer)
    assert not any("/search?" in path for path in calls)


def test_catalog_probe_invalidates_the_round_that_created_a_ban() -> None:
    catalog = probe("catalogprobe")
    statuses = iter(([], [{"indexerId": 1, "disabledTill": "later"}]))

    def answer(_base: str, _key: str, path: str, _timeout: float) -> Any:
        if path == "/api/v1/indexer":
            return [{"id": 1, "name": "one", "enable": True}]
        if path == "/api/v1/indexerstatus":
            return next(statuses)
        return []

    with pytest.raises(RuntimeError, match="замер недействителен"):
        catalog.measure("http://p", "key", "movie", 1, answer)
