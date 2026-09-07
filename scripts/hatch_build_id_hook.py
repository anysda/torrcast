"""Хук сборки колеса: печатает хэш `HEAD` исходного дерева в собранную копию метки.

`torrcast/adapters/health/build_id.py` сам умеет спросить живой git, но только когда
рядом с установленным модулем реально лежит `.git` - а обычная (не `-e`) установка
`pip install <каталог>` копирует файлы в колесо и `.git` с собой не берёт. Именно так
ставят на стенды: тем же способом, что и продукт. Хук читает `HEAD` исходного дерева
ДО того, как колесо собрано, и подставляет хэш в копию файла внутри архива - исходник
на диске при этом не трогается ни на миг.

Архива без `.git` (скачанный zip исходников, тарбол выпуска) хук не касается: хэша
взять неоткуда, колесо получит тот же `build_id.py`, что лежал в исходнике - для
тарбола выпуска это уже готовое клеймо `scripts/release.sh`, для голого зип-архива -
честный `None`.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.wheel import WheelBuilderConfig

#: Путь метки внутри пакета - относительно корня проекта и внутри самого колеса.
_TARGET = "torrcast/adapters/health/build_id.py"

#: Тот же плейсхолдер, что держит исходник и подставляет `scripts/release.sh` -
#: если он уже заменён (тарбол выпуска), хук молчит и колесо несёт готовое клеймо.
_PLACEHOLDER = re.compile(r"^BAKED_BUILD_ID: str \| None = None$", re.MULTILINE)


class BuildIdHook(BuildHookInterface[WheelBuilderConfig]):
    """Подставляет хэш `HEAD` в копию `build_id.py`, идущую в собранное колесо."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Готовит подменённую копию файла и просит сборщика включить её вместо исходной."""
        source = Path(self.root) / _TARGET
        head = _head_hash(Path(self.root))
        if head is None or not source.is_file():
            return
        text = source.read_text(encoding="utf-8")
        replacement = f'BAKED_BUILD_ID: str | None = "{head}"'
        patched, count = _PLACEHOLDER.subn(replacement, text)
        if count != 1:
            return
        staged = Path(tempfile.mkdtemp(prefix="torrcast-build-id-")) / "build_id.py"
        staged.write_text(patched, encoding="utf-8")
        build_data.setdefault("force_include", {})[str(staged)] = _TARGET


def _head_hash(root: Path) -> str | None:
    """Короткий хэш `HEAD` дерева `root`; нет `git`, не репозиторий - `None`."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None
