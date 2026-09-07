"""Метка КОДА на диске - не номер выпуска, а хэш коммита, из которого он собран.

`torrcast/domain/version.py` держит номер выпуска, и тот не двигается от тега до
тега: снимок `dev` на любом расстоянии от последнего релиза отвечает тем же числом,
что и сам релиз. Разобрать по продукту, какой код тут выкачен, этим числом нельзя -
отсюда и эта метка. Тарбол выпуска несёт готовое клеймо (:data:`BAKED_BUILD_ID`,
подставляется `scripts/release.sh` РОВНО одной заменой прямо перед сборкой архива -
`.git` внутри тарбола нет и спросить его не у кого); git-чекаут (полоса
исполнителя, `git clone` из README) отвечает сам. Ни того ни другого - ``None``:
честный ответ «неоткуда узнать», а не выдуманное число.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Плейсхолдер рабочего дерева. `scripts/release.sh` подставляет сюда хэш тега перед
#: сборкой тарбола выпуска; в самом репозитории это значение не меняется руками.
BAKED_BUILD_ID: str | None = None


def build_id() -> str | None:
    """Клеймо тарбола выпуска либо хэш ``HEAD`` живого git-чекаута; иначе ``None``."""
    if BAKED_BUILD_ID is not None:
        return BAKED_BUILD_ID
    here = Path(__file__).resolve()
    for ancestor in (here, *here.parents):
        if (ancestor / ".git").exists():
            return _git_build_id(ancestor)
    return None


def _git_build_id(root: Path) -> str | None:
    """Хэш ``HEAD`` и грязь рабочего дерева git-чекаута; любой отказ - ``None``."""
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return f"{head}+dirty" if dirty else head
