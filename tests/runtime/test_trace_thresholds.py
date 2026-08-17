"""Снимок порогов для ленты: каждое число названо вместе с тем, откуда оно взято."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.domain.config import Config
from torrcast.domain.profile import ANDROID_TV
from torrcast.domain.tune import tune
from torrcast.runtime.trace_thresholds import trace_thresholds


def test_the_snapshot_keeps_the_named_profile_and_the_explicit_config_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Профиль назван руками, порог написан руками - и то и другое стоит в ленте."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"receiver_profile": "androidtv", "recode_head_wait": 7.0}), encoding="utf-8"
    )
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))
    raw = Config.from_json(json.loads(path.read_text("utf-8")))

    snapshot = trace_thresholds(tune(raw, ANDROID_TV), ANDROID_TV)

    assert snapshot["profile_source"] == "назван руками: receiver_profile=androidtv"
    assert snapshot["threshold_sources"]["recode_head_wait"] == "написан в конфиге"  # type: ignore[index]
    assert snapshot["thresholds"]["recode_at_mbit"] == 28.0  # type: ignore[index]


def test_the_snapshot_does_not_name_a_profile_the_config_never_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ключ написан с ошибкой: играет осторожный, и в ленте стоит это, а не «q70d»."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"receiver_profile": "bogus"}), encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))
    raw = Config(receiver_profile="bogus")
    chosen = detector.detect(raw)

    snapshot = trace_thresholds(tune(raw, chosen.profile), chosen.profile)

    assert snapshot["profile_source"] == "профиля «bogus» нет - беру осторожный"


def test_a_config_broken_by_hand_mid_show_does_not_kill_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Снимок берётся на КАЖДОЙ серии: битый файл - молчание, а не погасший юнит."""
    path = tmp_path / "config.json"
    path.write_text('{"receiver_profile": "androidtv",}', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    assert trace_thresholds(Config(), ANDROID_TV) == {"profile_source": "конфиг не прочитан"}
