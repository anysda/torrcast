"""Выбор профиля приёмника для щупов тем же способом, что у показа."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.profile import Choice, detect, tune
from torrcast.state import Config


def add_argument(parser: argparse.ArgumentParser) -> None:
    """Добавить ручное переопределение профиля приёмника."""
    parser.add_argument("--profile", metavar="КЛЮЧ", help="профиль приёмника, например androidtv")


def choose(config: Config, named: str | None) -> tuple[Config, Choice]:
    """Выбрать, назвать и наложить профиль на настройки щупа."""
    if named is not None:
        config = replace(config, receiver_profile=named)
    choice = detect(config)
    print(f"профиль приёмника: {choice.profile.key} ({choice.profile.title}); {choice.how}")
    return tune(config, choice.profile), choice
