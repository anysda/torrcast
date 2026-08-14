"""Связь номера из ``cast releases`` с показанной раздачей."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from torrcast.parse import Release
from torrcast.state import _write_atomic, state_path


def info_hash(release: Release) -> str:
    """Инфохэш из магнита - устойчивое имя раздачи между двумя поисками."""
    xt = parse_qs(urlparse(release.magnet).query).get("xt", [])
    prefix = "urn:btih:"
    return next((item[len(prefix) :].lower() for item in xt if item.lower().startswith(prefix)), "")


def remember(query: str, releases: dict[str, list[Release]]) -> None:
    """Атомарно запомнить порядок последней таблицы этого запроса."""
    shown = {key: [info_hash(release) for release in ranked] for key, ranked in releases.items()}
    _write_atomic(_path(), {query: shown})


def recalled(query: str, picture: str, number: int) -> str:
    """Вернуть хэш, стоявший под номером в последней показанной таблице."""
    saved = _read(_path()).get(query, {})
    ranked = saved.get(picture, []) if isinstance(saved, dict) else []
    if not isinstance(ranked, list) or not all(isinstance(item, str) for item in ranked):
        return ""
    return ranked[number - 1] if 1 <= number <= len(ranked) else ""


def _path() -> Path:
    return state_path().with_name("release-pins.json")


def _read(path: Path) -> dict[str, Any]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}
