"""Проверка веса готового куска на последнем гейте выкладки."""

from pathlib import Path


def over_cap(path: Path, cap: int, missing: bool = False) -> bool:
    """Тяжелее ли файл потолка; ``missing`` задаёт решение для исчезнувшего файла."""
    try:
        return path.stat().st_size > cap
    except OSError:
        return missing
