"""Сторожа зрительских измерений ``web-acceptance.py`` без живого браузера."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def acceptance() -> ModuleType:
    """Загрузить сценарий как модуль: каталог ``scripts`` намеренно не пакет."""
    path = Path(__file__).parents[1] / "scripts" / "web-acceptance.py"
    spec = importlib.util.spec_from_file_location("web_acceptance", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Video:
    def __init__(self, current: float) -> None:
        self.current = current

    def count(self) -> int:
        return 1


class Page:
    def __init__(self, meter: dict[str, Any], current: float) -> None:
        self.meter = meter
        self.video = Video(current)

    def evaluate(self, expression: str) -> Any:
        return None if "const old" in expression else self.meter

    def locator(self, selector: str) -> Video:
        assert selector == "video"
        return self.video

    def eval_on_selector(self, selector: str, expression: str) -> float:
        assert selector == "video" and expression == "v => v.currentTime"
        return self.video.current

    def wait_for_timeout(self, timeout: int) -> None:
        raise AssertionError(f"кадр уже был, ждать {timeout} мс нельзя")


def test_кадр_берётся_из_rvfc_а_не_ready_state() -> None:
    module = acceptance()
    page = Page({"frame": 5.8, "start": 0.0, "playing": []}, 0.0)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})

    frame, meter = module._frame_measure(ctx, 1.0)

    assert frame == 5.8
    assert meter["start"] == 0.0


def test_скачок_закладки_не_становится_кадром_без_playing() -> None:
    module = acceptance()
    page = Page({"frame": None, "start": 4058.3, "playing": []}, 4058.7)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})

    frame, _ = module._frame_measure(ctx, 0.0)

    assert frame is None


def test_автопереход_не_принимает_последний_кадр_старой_серии() -> None:
    module = acceptance()
    page = Page(
        {"frame": 0.1, "start": 30.0, "playing": [0.1], "nextFrame": None},
        30.4,
    )
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})

    frame, _ = module._next_frame_measure(ctx, 0.0)

    assert frame is None


def test_автопереход_берёт_кадр_после_следующего_playing() -> None:
    module = acceptance()
    page = Page({"nextFrame": 4.2, "nextPlaying": 4.1}, 0.0)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})

    frame, meter = module._next_frame_measure(ctx, 1.0)

    assert frame == 4.2
    assert meter["nextPlaying"] == 4.1


def test_серия_контроля_не_прибита_к_s2e1() -> None:
    module = acceptance()

    assert module._episode_parts("s1e1") == (1, 1)
    assert module._episode_parts("episode 1") is None
