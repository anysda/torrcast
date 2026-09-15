"""Сторожа зрительских измерений ``web-acceptance.py`` без живого браузера."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


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


def _tiles(dim: int, live: int = 0, year: str = "") -> list[dict[str, Any]]:
    # Погашенная плитка на странице тоже несёт `data-tc-focusable` (`web/static/tile.js`):
    # гасит её только снятый `onActivate`, поэтому снимок видит её «живой».
    shown = [{"dim": True, "live": True, "text": ""} for _ in range(dim)]
    return shown + [{"dim": False, "live": True, "text": year} for _ in range(live)]


class SearchPage:
    """Выдача, которую страница пересобирает сразу после того, как её сосчитали."""

    def __init__(self, screens: dict[str, list[dict[str, Any]]]) -> None:
        self.screens = screens
        self.shown: list[dict[str, Any]] = []
        self.clock = 0.0

    def now(self) -> dict[str, Any]:
        return self.shown[0]

    def rerender(self) -> None:
        if len(self.shown) > 1:
            self.shown.pop(0)

    def goto(self, url: str, **_: Any) -> None:
        del url

    def get_by_placeholder(self, text: str, exact: bool) -> SearchNodes:
        del text, exact
        return SearchNodes(self, "field")

    def locator(self, selector: str) -> SearchNodes:
        return SearchNodes(self, selector)

    def evaluate(self, expression: str) -> dict[str, Any]:
        del expression
        screen = self.now()
        self.rerender()
        return screen

    def wait_for_timeout(self, timeout: int) -> None:
        self.clock += timeout / 1000


class SearchNodes:
    def __init__(self, page: SearchPage, selector: str) -> None:
        self.page, self.selector = page, selector

    @property
    def first(self) -> SearchNodes:
        return self

    def fill(self, text: str) -> None:
        self.page.shown = list(self.page.screens[text])

    def press(self, key: str) -> None:
        del key

    def wait_for(self, **_: Any) -> None:
        return None

    def count(self) -> int:
        if self.selector == "field":
            return 1
        screen = self.page.now()
        if self.selector == ".tc-searching":
            return int(screen["searching"])
        if self.selector == ".tc-nothing":
            return int(bool(screen["nothing"]))
        tiles = screen["tiles"]
        if self.selector == "[data-tc-tile]":
            self.page.rerender()
            return len(tiles)
        return sum(1 for tile in tiles if tile["live"])

    def inner_text(self) -> str:
        return str(self.page.now()["nothing"])


def _search(monkeypatch: pytest.MonkeyPatch, screens: dict[str, list[dict[str, Any]]]) -> Any:
    module = acceptance()
    page = SearchPage(screens)
    # Часы страницы вместо настоящих: несошедшийся поиск кончается за 15 с игрушечного времени.
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: page.clock))
    ctx = module.Ctx("http://example", page, False, Path("/tmp"), {"web.search.placeholder": "q"})
    return module.check_2_search(ctx)


def test_поиск_судит_один_снимок_выдачи_а_не_пересобранное_тело(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settled = {"searching": False, "nothing": ""}
    result = _search(
        monkeypatch,
        {
            "Мы": [{**settled, "tiles": _tiles(6, 2)}, {**settled, "tiles": _tiles(1, 1)}],
            "ывапрол": [{**settled, "tiles": _tiles(8)}, {**settled, "tiles": _tiles(3)}],
            "Интерстеллар": [{**settled, "tiles": _tiles(0, 3, "2014")}],
        },
    )

    assert "'Мы': плиток 8, погашено 6" in result.detail
    assert "'ывапрол': плиток 8, погашено 8, надпись ''" in result.detail
    assert result.ok is False


def test_пустая_выдача_с_надписью_установилась_и_зелёная(monkeypatch: pytest.MonkeyPatch) -> None:
    settled = {"searching": False, "nothing": ""}
    result = _search(
        monkeypatch,
        {
            "Мы": [{**settled, "tiles": _tiles(6, 2)}],
            "ывапрол": [{"searching": False, "tiles": [], "nothing": "Nothing found"}],
            "Интерстеллар": [{**settled, "tiles": _tiles(0, 3, "2014")}],
        },
    )

    assert "'ывапрол': плиток 0, погашено 0, надпись 'Nothing found'" in result.detail
    assert result.ok is True


def test_поиск_красный_когда_нет_открываемой_плитки_даже_без_погашения(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settled = {"searching": False, "nothing": ""}
    result = _search(
        monkeypatch,
        {
            "Мы": [{**settled, "tiles": [{"dim": False, "live": False, "text": ""}]}],
            "ывапрол": [{"searching": False, "tiles": [], "nothing": "Nothing found"}],
            "Интерстеллар": [{**settled, "tiles": _tiles(0, 3, "2014")}],
        },
    )

    assert "'Мы': плиток 1, погашено 0, надпись ''" in result.detail
    assert result.ok is False


class SeasonPage:
    """После снимка вкладок карточка заменяет DOM, как при фоновом ответе."""

    def __init__(self) -> None:
        self.current = ["Season 1", "Season 2"]
        self.clicked = ""

    def evaluate(self, expression: str, arg: str | None = None) -> Any:
        if "querySelectorAll('.tc-tab')" not in expression:
            raise AssertionError(expression)
        if arg is None:
            shot = [{"name": name} for name in self.current]
            self.current = ["Season 2", "Season 1"]
            return shot
        assert arg in self.current
        self.clicked = arg
        return True


def test_сезон_берётся_снимком_и_нажимается_после_пересборки() -> None:
    module = acceptance()
    page = SeasonPage()
    ctx = module.Ctx("http://example", page, False, Path("/tmp"), {})

    assert module._seasons(ctx) == ["Season 1", "Season 2"]
    assert module._click_season(ctx, "Season 2") is True
    assert page.clicked == "Season 2"
    assert ".nth(" not in inspect.getsource(module.check_7_series)
    assert ".nth(" not in inspect.getsource(module.check_13_texts)


class StallPage(Page):
    def __init__(self, waits: list[float]) -> None:
        super().__init__({}, 0.0)
        self.waits = waits

    def evaluate(self, expression: str) -> Any:
        if "Math.max(0, now - meter.waiting)" in expression:
            return {"waits": self.waits}
        return super().evaluate(expression)


def test_подгрузы_на_заглушке_видео_дают_ноль_или_два_замера() -> None:
    module = acceptance()
    clean = module.Ctx("http://example", StallPage([]), True, Path("/tmp"), {})
    broken = module.Ctx("http://example", StallPage([0.4, 1.25]), True, Path("/tmp"), {})

    assert module._wait_stalls(clean, 0) == ([], 0)
    waits, total = module._wait_stalls(broken, 0)
    assert waits == [0.4, 1.25]
    assert total == pytest.approx(1.65)
    assert "addEventListener('waiting'" in module._METER_JS


class MissingPlay(Video):
    def __init__(self) -> None:
        super().__init__(0)

    @property
    def first(self) -> MissingPlay:
        return self

    def wait_for(self, **_: Any) -> None:
        raise TimeoutError("absent")


class MissingPlayPage(Page):
    def locator(self, selector: str) -> Video:
        assert selector == "[data-tc-play]"
        return MissingPlay()


def test_нет_кнопки_показа_возвращает_приговор_а_не_таймаут() -> None:
    module = acceptance()
    ctx = module.Ctx("http://example", MissingPlayPage({}, 0), True, Path("/tmp"), {})

    clicked, detail = module._click_play(ctx, 0)

    assert clicked is None
    assert detail.startswith("кнопка показа не появилась за ")


def test_обычный_поиск_требует_сам_фильм_а_не_любую_плитку(monkeypatch: pytest.MonkeyPatch) -> None:
    settled = {"searching": False, "nothing": ""}
    result = _search(
        monkeypatch,
        {
            "Мы": [{**settled, "tiles": _tiles(6, 2)}],
            "ывапрол": [{"searching": False, "tiles": [], "nothing": "Nothing found"}],
            "Интерстеллар": [{**settled, "tiles": _tiles(0, 3, "2019")}],
        },
    )

    assert "'Интерстеллар': 2014 среди первых трёх открываемых False" in result.detail
    assert result.ok is False
