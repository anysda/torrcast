"""Выбор профиля приёмника для щупов тем же способом, что у показа."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.tune import tune


def add_argument(parser: argparse.ArgumentParser) -> None:
    """Добавить ручное переопределение профиля приёмника."""
    parser.add_argument("--profile", metavar="КЛЮЧ", help="профиль приёмника, например androidtv")


def choose(config: Config, named: str | None) -> tuple[Config, Choice]:
    """Выбрать, назвать и наложить профиль на настройки щупа."""
    if named is not None:
        config = replace(config, receiver_profile=named)
    choice = detector.detect(config)
    print(f"профиль приёмника: {choice.profile.key} ({choice.profile.title}); {choice.how}")
    return tune(config, choice.profile), choice
