"""Mirror of scripts/indexer-reconcile.py: the self-healing indexer reconciler (TC-1411)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load() -> ModuleType:
    path = Path(__file__).resolve().parent.parent / "scripts" / "indexer-reconcile.py"
    spec = importlib.util.spec_from_file_location("indexer_reconcile", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load()


def test_read_apikey_pulls_the_key_from_config_xml(tmp_path: Path) -> None:
    cfg = tmp_path / "config.xml"
    cfg.write_text("<Config><ApiKey>deadbeef</ApiKey></Config>", encoding="utf-8")
    assert MODULE.read_apikey(str(cfg)) == "deadbeef"


def test_read_apikey_is_none_when_absent(tmp_path: Path) -> None:
    cfg = tmp_path / "config.xml"
    cfg.write_text("<Config></Config>", encoding="utf-8")
    assert MODULE.read_apikey(str(cfg)) is None
    assert MODULE.read_apikey(str(tmp_path / "missing.xml")) is None


def test_load_manifest_keeps_only_named_entries(tmp_path: Path) -> None:
    manifest = tmp_path / "indexers.json"
    manifest.write_text('[{"name": "RuTor"}, {"x": 1}, "junk"]', encoding="utf-8")
    assert MODULE.load_manifest(str(manifest)) == [{"name": "RuTor"}]
    assert MODULE.load_manifest(str(tmp_path / "none.json")) == []


def test_reconcile_adds_only_the_missing_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Present indexers are left alone; the missing ones are re-POSTed by name."""
    posted: list[str] = []

    def record(url: str, key: str, body: dict[str, object]) -> bool:
        posted.append(str(body["name"]))
        return True

    monkeypatch.setattr(MODULE, "live_names", lambda url, key: {"RuTor"})
    monkeypatch.setattr(MODULE, "_post", record)
    manifest = [{"name": "RuTor"}, {"name": "RuTor names"}, {"name": "sukebei"}]
    added = MODULE.reconcile_once("http://x", "key", manifest)
    assert posted == ["RuTor names", "sukebei"]
    assert added == ["RuTor names", "sukebei"]


def test_reconcile_skips_the_round_when_prowlarr_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """No live list means we cannot tell what is missing: do nothing, try next round."""
    monkeypatch.setattr(MODULE, "live_names", lambda url, key: None)
    monkeypatch.setattr(MODULE, "_post", lambda *a: pytest.fail("must not POST blind"))
    assert MODULE.reconcile_once("http://x", "key", [{"name": "RuTor"}]) == []


def test_a_refused_post_is_not_counted_as_added(monkeypatch: pytest.MonkeyPatch) -> None:
    """A still-silent tracker makes Prowlarr refuse the POST: the indexer did not arrive."""
    monkeypatch.setattr(MODULE, "live_names", lambda url, key: set())
    monkeypatch.setattr(MODULE, "_post", lambda url, key, body: False)
    assert MODULE.reconcile_once("http://x", "key", [{"name": "RuTor"}]) == []


class _StopError(Exception):
    pass


def test_the_first_round_waits_out_the_install_retry_ladder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-697. The daemon must not ask a refused tracker while the install still does."""
    events: list[str] = []

    def nap(seconds: float) -> None:
        events.append(f"sleep {seconds:.0f}")
        if len(events) > 2:
            raise _StopError

    monkeypatch.setattr(MODULE.time, "sleep", nap)
    monkeypatch.setattr(MODULE, "read_apikey", lambda path: "key")
    monkeypatch.setattr(MODULE, "load_manifest", lambda path: [])

    def round_(*_args: object) -> list[str]:
        events.append("round")
        return []

    monkeypatch.setattr(MODULE, "reconcile_once", round_)
    with pytest.raises(_StopError):
        MODULE._run("http://x", "cfg", "man", 900.0, False, 3600.0)
    assert events[:3] == ["sleep 3600", "round", "sleep 900"]


def test_once_runs_a_single_round_with_no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    rounds: list[int] = []
    monkeypatch.setattr(MODULE.time, "sleep", lambda s: pytest.fail("--once must not wait"))
    monkeypatch.setattr(MODULE, "read_apikey", lambda path: "key")
    monkeypatch.setattr(MODULE, "load_manifest", lambda path: [])

    def round_(*_args: object) -> list[str]:
        rounds.append(1)
        return []

    monkeypatch.setattr(MODULE, "reconcile_once", round_)
    assert MODULE._run("http://x", "cfg", "man", 900.0, True, 3600.0) == 0
    assert rounds == [1]
