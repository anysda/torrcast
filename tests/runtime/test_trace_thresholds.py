"""Снимок порогов для ленты: каждое число названо вместе с тем, откуда оно взято."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.chromecast.scan.device import Device
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

    assert snapshot["profile_source"] == "manually named: receiver_profile=androidtv"
    assert snapshot["threshold_sources"]["recode_head_wait"] == "written in the config"  # type: ignore[index]
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

    assert snapshot["profile_source"] == 'no profile named "bogus" - falling back to cautious'


def test_a_config_broken_by_hand_mid_show_does_not_kill_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Снимок берётся на КАЖДОЙ серии: битый файл - молчание, а не погасший юнит."""
    path = tmp_path / "config.json"
    path.write_text('{"receiver_profile": "androidtv",}', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    assert trace_thresholds(Config(), ANDROID_TV) == {"profile_source": "config not read"}


def test_a_profile_from_the_receiver_passport_is_named_a_passport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Профиль взят из паспорта приёмника - и лента говорит «паспорт приёмника»,
    а не повторяет строку опроса с именами устройства."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tv": "10.0.0.77"}), encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))
    monkeypatch.setattr(
        detector,
        "_ask",
        lambda address, timeout=0.0: Device(address=address, maker="Xiaomi"),
    )
    detector.forget()
    try:
        snapshot = trace_thresholds(Config(), ANDROID_TV)
    finally:
        detector.forget()

    assert snapshot["profile_source"] == "receiver passport"


def test_a_handwritten_key_equal_to_the_cautious_default_is_named_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Случай из жизни: в конфиге ``recode_at_mbit: 10.0``, в ленте ``28.0`` - и по
    записи обязано быть видно, что ключ в файле ЕСТЬ и был молча проигнорирован."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"receiver_profile": "androidtv", "recode_at_mbit": 10.0}), encoding="utf-8"
    )
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))
    raw = Config.from_json(json.loads(path.read_text("utf-8")))

    snapshot = trace_thresholds(tune(raw, ANDROID_TV), ANDROID_TV)

    assert snapshot["thresholds"]["recode_at_mbit"] == 28.0  # type: ignore[index]
    assert snapshot["threshold_sources"]["recode_at_mbit"] == (  # type: ignore[index]
        "written in the config, but equal to the cautious one - profile androidtv"
    )
