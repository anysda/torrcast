"""Подпись прибора: одна грамматика на вывод щупа и на комментарий рядом с числом.

Проверяется ровно то, ради чего подпись заведена: её нельзя написать так, чтобы сторож
дерева её не разобрал, - иначе подпись отличалась бы от молчания только на глаз.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def tool(name: str) -> ModuleType:
    """Загрузить инструмент из ``scripts/``: пакетом каталог не является, путь известен."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_подпись_называет_прибор_тракт_и_место() -> None:
    """Три поля обязательны, числа прогона приписываются тем же разделителем."""
    stamp = tool("probestamp")

    assert stamp.stamp("tvprobe", "mpegts", "TC-620") == "снято: tvprobe · mpegts · TC-620"
    assert stamp.stamp("tvprobe", "fmp4", "приёмник androidtv", ["вес 28.0 МБ"]) == (
        "снято: tvprobe · fmp4 · приёмник androidtv · вес 28.0 МБ"
    )


def test_подпись_щупа_читается_сторожем_дерева() -> None:
    """🔴 Половинки заведены под один вопрос и обязаны сходиться буква в букву.

    Щуп печатает подпись, человек переносит её к числу, сторож её спрашивает. Разъедься
    грамматика - и перенесённая подпись читалась бы как ненаписанная, то есть вопрос
    «чем снято» снова отвечался бы историей git.
    """
    stamp = tool("probestamp")
    sign = tool("probesign")
    said = stamp.stamp("tvprobe", "mpegts", "TC-620", ["вес 28.0 МБ", "длина 15.0 с"])

    assert not sign.unsigned(f"X = Profile(key='k', max_segment_bytes=1)  # {said}\n")


def test_подпись_не_принимает_неназванный_прибор_и_тракт() -> None:
    """Прибор и тракт - из закрытых списков: самоназвание в подписи не прибор."""
    stamp = tool("probestamp")

    with pytest.raises(ValueError, match="прибор"):
        stamp.stamp("глазами", "mpegts", "TC-620")
    with pytest.raises(ValueError, match="тракт"):
        stamp.stamp("tvprobe", "hls", "TC-620")
    with pytest.raises(ValueError, match="места замера"):
        stamp.stamp("tvprobe", "mpegts", "  ")
