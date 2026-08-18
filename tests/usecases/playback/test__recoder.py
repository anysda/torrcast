"""Зеркало подъёма кодировщика тяжёлых кусков: когда он нужен и когда честно отказывает."""

from __future__ import annotations

from pathlib import Path

import pytest

import torrcast.usecases.playback._show_state as _state
from tests.usecases.playback.world import film_keys, grid
from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS
from torrcast.recode import Encode, Recoder, Weights
from torrcast.stream import Grid
from torrcast.usecases.playback._recoder import _recoder


@pytest.fixture(autouse=True)
def _tract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_state, "film_keys", lambda source: film_keys())
    monkeypatch.setattr(_state, "weights_of", Weights.of)
    monkeypatch.setattr(_state, "Recoder", Recoder)
    monkeypatch.setattr(_state, "Encode", Encode)


def test_recoding_switched_off_needs_no_recoder(tmp_path: Path) -> None:
    """Перекод выключен настройкой - кодировщика нет, и спрашивать карту незачем."""
    assert _recoder("http://ts", 0, grid(), tmp_path, Config(recode=False)) is None


def test_a_grid_not_on_keyframes_is_a_spoken_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Сетка не по опорным кадрам - границы не совпадут с картой, и об этом говорят вслух."""
    made = _recoder("http://ts", 0, Grid.uniform(300.0), tmp_path, Config(recode=True))

    assert made is None
    assert "сетка не по опорным кадрам" in capsys.readouterr().out


def test_a_keymap_that_never_came_is_a_spoken_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карту снять не удалось - играем как есть, и это сказано, а не молча."""

    def dead(_source: str) -> object:
        raise InfraError("рой молчит")

    monkeypatch.setattr(_state, "film_keys", dead)

    made = _recoder("http://ts", 0, grid(), tmp_path, Config(recode=True))

    assert made is None
    assert "профиль тяжести не снят" in capsys.readouterr().out


def test_a_healthy_map_raises_the_recoder_and_says_its_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карта есть - кодировщик поднимается, а профиль тяжести называется числом."""
    made = _recoder(
        "http://ts", 0, grid(), tmp_path, Config(recode=True), video_mbit=8.0, profile=CAUTIOUS
    )

    assert made is not None
    assert made.encode.mbit > 0.0
    assert "профиль тяжести:" in capsys.readouterr().out


def test_a_map_without_offsets_is_a_spoken_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карта прошлой версии смещений не несёт - профиля не построить, и это сказано."""
    monkeypatch.setattr(_state, "film_keys", lambda source: film_keys()._replace(offset=[]))

    made = _recoder("http://ts", 0, grid(), tmp_path, Config(recode=True))

    assert made is None
    assert "карта без смещений" in capsys.readouterr().out
