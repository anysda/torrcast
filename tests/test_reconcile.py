"""Mirror of scripts/indexer-reconcile.py: the indexer upkeep service (TC-1411)."""

import importlib.util
import json
import subprocess
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


def _owed(tmp_path: Path, *entries: dict[str, object]) -> str:
    path = tmp_path / "indexers.json"
    path.write_text(json.dumps(list(entries)), encoding="utf-8")
    return str(path)


def _names(path: str) -> list[str]:
    return [str(e["name"]) for e in MODULE.load_manifest(path)]


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


def test_reconcile_adds_the_missing_and_crosses_out_what_arrived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Present indexers are crossed out; the missing ones are re-POSTed and crossed out too."""
    posted: list[str] = []

    def record(url: str, key: str, body: dict[str, object]) -> bool:
        posted.append(str(body["name"]))
        return True

    monkeypatch.setattr(MODULE, "live_names", lambda url, key: {"RuTor"})
    monkeypatch.setattr(MODULE, "_post", record)
    path = _owed(tmp_path, {"name": "RuTor"}, {"name": "RuTor names"}, {"name": "Knaben"})
    assert MODULE.reconcile_once("http://x", "key", path) == ["RuTor names", "Knaben"]
    assert posted == ["RuTor names", "Knaben"]
    assert _names(path) == []


def test_an_indexer_deleted_by_hand_after_it_arrived_is_not_added_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-1411. A human decided: once seen in Prowlarr, its later absence is respected."""
    monkeypatch.setattr(MODULE, "_post", lambda *a: pytest.fail("deleted by hand, must stay"))
    path = _owed(tmp_path, {"name": "Knaben", "retry": True})
    monkeypatch.setattr(MODULE, "live_names", lambda url, key: {"Knaben"})
    MODULE.reconcile_once("http://x", "key", path)
    monkeypatch.setattr(MODULE, "live_names", lambda url, key: set())
    for _ in range(2):
        assert MODULE.reconcile_once("http://x", "key", path) == []


def test_a_narrow_indexer_is_never_asked_but_stays_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-697. A narrow source is asked once per install; doctor still needs its name."""
    monkeypatch.setattr(MODULE, "live_names", lambda url, key: set())
    monkeypatch.setattr(MODULE, "_post", lambda *a: pytest.fail("narrow must not be re-asked"))
    path = _owed(tmp_path, {"name": "sukebei", "retry": False})
    assert MODULE.reconcile_once("http://x", "key", path) == []
    assert _names(path) == ["sukebei"]


def test_the_retry_mark_does_not_reach_prowlarr(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, object]] = []

    class _Answer:
        def close(self) -> None:
            pass

    def urlopen(request: object, timeout: float) -> _Answer:
        sent.append(json.loads(request.data))  # type: ignore[attr-defined]
        return _Answer()

    monkeypatch.setattr(MODULE.urllib.request, "urlopen", urlopen)
    assert MODULE._post("http://x", "key", {"name": "RuTor", "retry": True})
    assert sent == [{"name": "RuTor"}]


def test_reconcile_skips_the_round_when_prowlarr_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No live list means we cannot tell what is missing: do nothing, try next round."""
    monkeypatch.setattr(MODULE, "live_names", lambda url, key: None)
    monkeypatch.setattr(MODULE, "_post", lambda *a: pytest.fail("must not POST blind"))
    path = _owed(tmp_path, {"name": "RuTor"})
    assert MODULE.reconcile_once("http://x", "key", path) == []
    assert _names(path) == ["RuTor"]


def test_a_refused_post_is_not_counted_as_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A still-silent tracker makes Prowlarr refuse the POST: the indexer stays owed."""
    monkeypatch.setattr(MODULE, "live_names", lambda url, key: set())
    monkeypatch.setattr(MODULE, "_post", lambda url, key, body: False)
    path = _owed(tmp_path, {"name": "RuTor"})
    assert MODULE.reconcile_once("http://x", "key", path) == []
    assert _names(path) == ["RuTor"]


@pytest.mark.machine
def test_only_a_live_install_retry_holds_the_trackers(tmp_path: Path) -> None:
    """Our own pid with its start time counts; a reused pid or another job does not."""
    job = subprocess.Popen(["sleep", "30"])
    try:
        started = MODULE._started(str(job.pid))
        assert started
        pids = tmp_path / "late.pids"
        pids.write_text(
            f"{job.pid}\t{started}\tretry_add_indexers\n"
            f"{job.pid}\tMon Jan  1 00:00:00 2001\tadd_twins\n"
            f"{job.pid}\t{started}\tsetup_facts\n",
            encoding="utf-8",
        )
        assert MODULE.install_retrying(str(pids)) == [str(job.pid)]
    finally:
        job.kill()
        job.wait()
    assert MODULE.install_retrying(str(pids)) == []
    assert MODULE.install_retrying(str(tmp_path / "none")) == []


class _StopError(Exception):
    pass


def _drive(monkeypatch: pytest.MonkeyPatch, busy: list[list[str]]) -> list[str]:
    """Run the loop against a fake clock; ``busy`` is what each look finds alive."""
    events: list[str] = []
    clock = [0.0]

    def nap(seconds: float) -> None:
        events.append(f"sleep {seconds:.0f}")
        clock[0] += seconds
        if len(events) > 8:
            raise _StopError

    def round_(url: str, key: str, path: str, ask: bool = True) -> list[str]:
        events.append("ask" if ask else "look")
        return []

    monkeypatch.setattr(MODULE.time, "sleep", nap)
    monkeypatch.setattr(MODULE.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(MODULE, "read_apikey", lambda path: "key")
    monkeypatch.setattr(MODULE, "install_retrying", lambda path: busy.pop(0) if busy else [])
    monkeypatch.setattr(MODULE, "reconcile_once", round_)
    with pytest.raises(_StopError):
        MODULE._run("http://x", "cfg", "man", "pids", 900.0)
    return events


def test_after_a_reboot_the_first_round_asks_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 TC-1411. No install retries alive: no hour of waiting, then the normal pace."""
    events = _drive(monkeypatch, [])
    assert events[:4] == ["ask", "sleep 60", "look", "sleep 60"]
    assert events.count("ask") == 1  # the next ask is 900 s away, not yet


def test_trackers_wait_only_while_the_install_retries_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-697. Two asks at one tracker in the same minute only extend its ban."""
    events = _drive(monkeypatch, [["41"], ["41"]])
    assert events[:5] == ["look", "sleep 60", "look", "sleep 60", "ask"]
