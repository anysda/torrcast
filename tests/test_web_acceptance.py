"""Сторожа зрительских измерений ``web-acceptance.py`` без живого браузера."""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import json
import os
import sys
import time
import urllib.parse
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


class HomeNode:
    """Минимальный locator для заглушки, заголовков и пустой истории главной."""

    def __init__(self, amount: int) -> None:
        self.amount = amount

    @property
    def first(self) -> HomeNode:
        return self

    def count(self) -> int:
        return self.amount

    def is_visible(self) -> bool:
        return bool(self.amount)

    def locator(self, _selector: str) -> HomeNode:
        return HomeNode(self.amount)


class HomePage:
    """Главная с честной заглушкой и двумя названными полками в DOM."""

    def __init__(self) -> None:
        self.clock = 0.0

    def goto(self, _url: str, **_: Any) -> None:
        return None

    def locator(self, selector: str) -> HomeNode:
        return HomeNode(1 if selector in {".tc-tile-skeleton", "#tc-body"} else 0)

    def get_by_text(self, text: str, exact: bool) -> HomeNode:
        assert exact
        return HomeNode(1 if text in {"Loading_", "New", "Popular"} else 0)

    def wait_for_timeout(self, timeout: int) -> None:
        # Пустую полку доводим до минутного приговора шестью шагами вместо 600.
        self.clock += timeout / 10 if timeout == 100 else timeout / 1000


@pytest.mark.parametrize(
    ("tiles", "state", "arrival"),
    (
        (14, "OK", "настоящие плитки за 0.0 с (потолок 60 с)"),
        (0, "FAIL", "полка пустая или не приехала за 60 с"),
        (20, "OK", "настоящие плитки за 0.0 с (потолок 60 с)"),
    ),
)
def test_главная_отличает_короткую_полку_от_неприехавшей(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tiles: int,
    state: str,
    arrival: str,
) -> None:
    module = acceptance()
    page = HomePage()
    body = json.dumps({"fresh": list(range(tiles)), "popular": list(range(tiles))}).encode()

    def get(url: str, timeout: float = 10.0) -> tuple[int, bytes]:
        del timeout
        if url == "http://example/":
            return 200, b""
        if url.endswith("/api/shelves"):
            return 200, body
        if url.endswith("/api/history"):
            return 200, b'{"items": []}'
        raise AssertionError(url)

    monkeypatch.setattr(module, "_get", get)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: page.clock))
    ctx = module.Ctx(
        "http://example",
        page,
        False,
        Path("/tmp"),
        {
            "web.shelf.loading": "Loading_",
            "web.shelf.continue_watching": "Continue",
            "web.shelf.new": "New",
            "web.shelf.popular": "Popular",
        },
    )

    result = module.check_1_home(ctx)
    module._print([result])

    assert result.ok is (state == "OK")
    assert capsys.readouterr().out.splitlines()[0] == (
        f"[ 1] Главная    {state:<8} GET / -> 200; "
        f"скелет и Loading_ за 0.0 с (потолок 10 с); {arrival}; "
        "полки выдачи в DOM по тексту 2/2 (new=1, popular=1); "
        "скелет «Продолжить» снят за 0.0 с; "
        "continue_watching=0, плиток 0; GET /api/history -> 200, записей 0; "
        f"GET /api/shelves -> 200, полок 2, плиток {{'fresh': {tiles}, 'popular': {tiles}}}"
    )


class ContinueShelf(HomeNode):
    """Полка «Продолжить»: шесть заглушек, пока стоит скелет, потом лента истории."""

    def __init__(self, page: ContinuePage) -> None:
        super().__init__(1)
        self.page = page

    def locator(self, selector: str) -> HomeNode:
        if selector.startswith("xpath="):
            return self
        assert selector == "[data-tc-tile]"
        return HomeNode(6 if self.page.waits() else self.page.history)


class ContinuePage(HomePage):
    """Главная, где выдача стоит сразу, а история приходит к ``answered`` секунде."""

    def __init__(self, history: int, answered: float | None) -> None:
        super().__init__()
        self.history = history
        self.answered = answered

    def waits(self) -> bool:
        return self.answered is None or self.clock < self.answered

    def locator(self, selector: str) -> HomeNode:
        if selector == '[data-tc-waits="continue"]':
            return HomeNode(1 if self.waits() else 0)
        if selector == '[data-tc-waits="continue"] [data-tc-tile]':
            return HomeNode(6 if self.waits() else 0)
        return super().locator(selector)

    def get_by_text(self, text: str, exact: bool) -> HomeNode:
        if text == "Continue":
            return ContinueShelf(self)
        return super().get_by_text(text, exact)

    def wait_for_timeout(self, timeout: int) -> None:
        self.clock += timeout / 1000


def _continue_home(monkeypatch: pytest.MonkeyPatch, history: int, answered: float | None) -> Any:
    module = acceptance()
    page = ContinuePage(history, answered)
    shelves = json.dumps({"fresh": list(range(20)), "popular": list(range(20))}).encode()
    items = json.dumps({"items": list(range(history))}).encode()

    def get(url: str, timeout: float = 10.0) -> tuple[int, bytes]:
        del timeout
        if url == "http://example/":
            return 200, b""
        if url.endswith("/api/shelves"):
            return 200, shelves
        if url.endswith("/api/history"):
            return 200, items
        raise AssertionError(url)

    monkeypatch.setattr(module, "_get", get)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: page.clock))
    english = {
        "web.shelf.loading": "Loading_",
        "web.shelf.continue_watching": "Continue",
        "web.shelf.new": "New",
        "web.shelf.popular": "Popular",
    }
    return module.check_1_home(module.Ctx("http://example", page, False, Path("/tmp"), english))


def test_продолжить_считается_после_снятия_скелета(monkeypatch: pytest.MonkeyPatch) -> None:
    # Замер на стенде: полки к 0.6 с, холодная история к 5.1 с, до неё в ленте 6 заглушек.
    result = _continue_home(monkeypatch, history=24, answered=5.05)

    assert result.ok, result.detail
    assert "скелет «Продолжить» снят за 5.1 с" in result.detail
    assert "continue_watching=1, плиток 24; GET /api/history -> 200, записей 24" in result.detail


def test_неснятый_скелет_продолжить_красный(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _continue_home(monkeypatch, history=6, answered=None)

    assert not result.ok
    assert "скелет «Продолжить» не снят за 20 с, заглушек 6" in result.detail


class CardAnswer:
    """Ответ ``/api/card/`` с одним словом про дорожки."""

    def __init__(self, key: str, pending: bool) -> None:
        self.url = f"http://example/api/card/{key}?query=x&wait=1&voices=1"
        self.pending = pending

    def json(self) -> dict[str, Any]:
        return {"voices_pending": self.pending, "voices": []}


class CardNode:
    """Locator карточки: плитка, тело, меню озвучек и «Играть» по часам страницы."""

    def __init__(self, page: CardPage, selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> CardNode:
        return self

    def count(self) -> int:
        if self.selector == "[data-tc-audio-option]":
            return self.page.voices if self.page.settled() else 0
        return 1

    def click(self) -> None:
        self.page.clicked = True

    def get_attribute(self, name: str) -> str:
        assert name == "data-tc-key"
        return "movie:интерстеллар:2014"

    def wait_for(self, **_: Any) -> None:
        return None

    def is_enabled(self) -> bool:
        return True

    def locator(self, selector: str) -> CardNode:
        return CardNode(self.page, selector)


class CardPage:
    """Карточка, у которой описание стоит сразу, а дорожки дочитываются к ``settles``."""

    def __init__(self, voices: int, settles: float | None, foreign_last: bool = False) -> None:
        self.clock = 0.0
        self.foreign_last = foreign_last
        self.voices = voices
        self.settles = settles
        self.clicked = False
        self.handlers: list[Any] = []
        self.sent = 0

    def settled(self) -> bool:
        return self.settles is not None and self.clock >= self.settles

    def locator(self, selector: str) -> CardNode:
        return CardNode(self, selector)

    def on(self, event: str, handler: Any) -> None:
        assert event == "response"
        self.handlers.append(handler)

    def remove_listener(self, event: str, handler: Any) -> None:
        assert event == "response"
        self.handlers.remove(handler)

    def wait_for_timeout(self, timeout: int) -> None:
        self.clock += timeout / 1000
        if not self.clicked:
            return
        key = urllib.parse.quote("movie:интерстеллар:2014", safe="")
        # Чужая карточка (прогрев соседней плитки) говорит своё и не в счёт.
        answers = [CardAnswer("movie%3Aother%3A2001", False), CardAnswer(key, not self.settled())]
        if self.foreign_last:
            answers.reverse()
        for handler in list(self.handlers):
            for answer in answers:
                handler(answer)
        self.sent += 1


def _card(
    monkeypatch: pytest.MonkeyPatch, voices: int, settles: float | None, foreign_last: bool = False
) -> Any:
    module = acceptance()
    page = CardPage(voices, settles, foreign_last)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: page.clock))
    monkeypatch.setattr(
        module,
        "_card_texts",
        lambda _ctx: {"title": "Интерстеллар", "description": "Про космос", "rating": "IMDb 8.7"},
    )
    result = module.check_3_card(module.Ctx("http://example", page, False, Path("/tmp"), {}), True)
    assert not page.handlers
    return result


def test_карточка_судит_озвучки_после_дочитанных_дорожек(monkeypatch: pytest.MonkeyPatch) -> None:
    # Замер на стенде: описание к первому ответу, voices_pending снят на 30.7 с от клика.
    result = _card(monkeypatch, voices=3, settles=30.7)

    assert result.ok, result.detail
    assert "дорожки дочитаны за 30.8 с от клика; озвучек 3" in result.detail


def test_недочитанные_к_потолку_дорожки_красные(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _card(monkeypatch, voices=3, settles=None)

    assert not result.ok
    assert "дорожки не дочитаны за 90 с от клика (voices_pending=True" in result.detail


def test_чужой_дочитанный_ответ_после_своего_не_снимает_ожидание(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Своя карточка всё время отвечает voices_pending=true, а соседняя плитка следом за
    # ней - false. Прибор, который слушает любую карточку, взял бы чужое «дочитано».
    result = _card(monkeypatch, voices=3, settles=None, foreign_last=True)

    assert not result.ok
    assert "дорожки не дочитаны за 90 с от клика (voices_pending=True" in result.detail


def test_дочитанные_без_озвучек_красные(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _card(monkeypatch, voices=0, settles=13.9)

    assert not result.ok
    assert "дорожки дочитаны за 14.0 с от клика; озвучек 0" in result.detail


def test_таймаут_стартовой_записи_называет_фактическое_окно(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = acceptance()
    row = SimpleNamespace(first=SimpleNamespace(click=lambda: None), count=lambda: 1)
    page = SimpleNamespace(locator=lambda _selector: row)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})
    clock = iter((0.0, module._SHOW_UP_WAIT + 1.0))

    monkeypatch.setattr(module, "_playback_guard", lambda *_args: None)
    monkeypatch.setattr(module, "_open_card_by_page", lambda *_args: None)
    monkeypatch.setattr(module, "_card_key", lambda _ctx: "key")
    monkeypatch.setattr(module, "_place_of", lambda *_args: ("s1e2", 300.0))
    monkeypatch.setattr(module, "_episode_season", lambda *_args: None)
    monkeypatch.setattr(module, "_stop_show", lambda _ctx: None)
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _seconds: None),
    )

    result = module.check_36_place_survives(ctx)

    assert not result.ok
    assert result.detail == "стартовая запись s1e1 не легла за 360 с"


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


@pytest.mark.parametrize(("gap", "ok"), [(1.82, True), (3.0, True), (9.67, False), (None, False)])
def test_автопереход_судит_стык_от_ended_до_кадра(gap: float | None, ok: bool) -> None:
    """Стык 9.67 с без подгрузов после кадра - красный: переход судится своим числом."""
    module = acceptance()
    pairs = ((1, 1), (1, 2))

    assert module._autoplay_ok(pairs, 11.5, gap, True, []) is ok
    assert module._autoplay_ok(pairs, 11.5, 1.82, True, [(1.0, 0.2)]) is False
    assert module._autoplay_ok(((1, 1), (1, 1)), 11.5, 1.82, True, []) is False


def test_пустое_название_не_открывает_чужую_карточку() -> None:
    """Пустой поиск не сужает выдачу: карточка не открывается, страница не трогается."""
    module = acceptance()
    ctx = module.Ctx("http://example", None, True, Path("/tmp"), {})

    assert "пустое название" in module._open_card_by_page(ctx, " ")


def test_прибор_отказывает_на_пустом_сериале(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = acceptance()
    monkeypatch.setattr(sys, "argv", ["web-acceptance.py", "--only", "8", "--series-title", ""])

    with pytest.raises(SystemExit) as stop:
        module.main()

    assert stop.value.code == 2
    assert "--series-title пустой" in capsys.readouterr().err


def test_автопереход_называет_сыгранный_сериал() -> None:
    """Строка п.8 подписана тем, что сыграл показ, а не тем, что заказали."""
    module = acceptance()

    assert module._played({"title": "Рик и Морти"}, {"title": "Призрак"}) == "«Призрак»"
    assert module._played({"title": "Рик и Морти"}, {}) == "«Рик и Морти»"
    assert module._played({}, {}) == "без названия"


def test_автопереход_берёт_первую_видимую_серию_сезона_закладки(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Карточка сериала открыта на сезоне закладки: после s2e1 пункта 7 строки s1e1 нет."""
    module = acceptance()
    clicked: list[str] = []
    shown = ["s2e1", "s2e2"]

    def rows(selector: str) -> SimpleNamespace:
        found = [name for name in shown if selector in ("[data-tc-episode]:visible", name)]
        first = SimpleNamespace(
            wait_for=lambda **_kwargs: None,
            get_attribute=lambda _name: found[0],
            click=lambda: clicked.append(found[0]),
        )
        return SimpleNamespace(first=first, count=lambda: len(found))

    page = SimpleNamespace(locator=rows)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})
    monkeypatch.setattr(module, "_playback_guard", lambda *_args: None)
    monkeypatch.setattr(module, "_open_card_by_page", lambda *_args: None)
    monkeypatch.setattr(module, "_await_playback", lambda _ctx: False)

    result = module.check_8_autoplay(ctx)

    assert clicked == ["s2e1"]
    assert result.detail == "первого кадра серии так и не было"


@pytest.mark.parametrize(
    ("box", "same"),
    [("/hls/index.m3u8", True), ("http://192.0.2.60:8080/hls/index.m3u8", True), ("/hls/x", False)],
)
def test_url_ящика_сверяется_по_потоку_а_не_по_узлу(
    monkeypatch: pytest.MonkeyPatch, box: str, same: bool
) -> None:
    """Вкладка берёт поток с узла страницы (``TCPlayerBox.near``), ящик даёт свою дверь."""
    module = acceptance()
    page = SimpleNamespace(evaluate=lambda _js: "http://example:8479/hls/index.m3u8")
    ctx = module.Ctx("http://example:8479", page, True, Path("/tmp"), {})
    body = json.dumps({"url": box}).encode()
    monkeypatch.setattr(module, "_get", lambda _url: (200, body))

    ok, _detail = module._cast_url_matches(ctx)

    assert ok is same


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


class EpisodeRow:
    """Строка серии, клик по которой пишется в общий журнал рядом с остановкой показа."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    @property
    def first(self) -> EpisodeRow:
        return self

    def count(self) -> int:
        return 1

    def wait_for(self, **_: Any) -> None:
        return None

    def click(self) -> None:
        self.log.append("клик")


def test_серия_гасит_поднятый_кликом_показ(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пункт 7 последний в прогоне: показ, который включил его клик, он и гасит."""
    module = acceptance()
    log: list[str] = []
    row = EpisodeRow(log)
    page = SimpleNamespace(locator=lambda _selector: row, wait_for_function=lambda *_a, **_k: None)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {}, series_target="s1e1")
    monkeypatch.setattr(module, "_open_card_by_page", lambda *_args: None)
    monkeypatch.setattr(module, "_await_seasons", lambda _ctx: ["Season 1"])
    monkeypatch.setattr(module, "_click_season", lambda *_args: True)
    monkeypatch.setattr(module, "_playback_guard", lambda *_args: None)
    monkeypatch.setattr(module, "_get", lambda _url: (200, b'{"season": 1, "episode": 1}'))
    monkeypatch.setattr(module, "_stop_show", lambda _ctx: log.append("стоп"))

    result = module.check_7_series(ctx)

    assert result.ok, result.detail
    assert log == ["клик", "стоп"]


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
    def __init__(
        self,
        waits: list[float],
        seen: list[bool],
        frozen: list[bool] | None = None,
        hold: float | None = None,
    ) -> None:
        super().__init__({}, 0.0)
        self.waits = waits
        self.seen = seen
        self.frozen = frozen
        self.hold = hold

    def evaluate(self, expression: str) -> Any:
        if "Math.max(0, now - meter.waiting)" in expression:
            meter: dict[str, Any] = {"waits": self.waits, "seen": self.seen}
            if self.frozen is not None:
                meter["frozen"] = self.frozen
            if self.hold is not None:
                meter["hold"] = self.hold
            return meter
        return super().evaluate(expression)


def test_замирание_без_спиннера_при_пустом_буфере_подгруз() -> None:
    """Тепло-2 на стенде: «Оно» с закладки встало на 140.75, буфера впереди 0, спиннера нет.

    Прибор писал «подгрузы 0; без спиннера в кадре 1» на 179 с и давал П.4 OK. Для
    зрителя замирание то же, что подгруз: головка стоит, впереди пусто, дольше срока
    плеера ``hold`` (``TCPlayer.STALL_SHOW_MS``). Такая заминка обязана уйти в подгрузы,
    а с ними П.4 и П.5 красные (``and not waits``). Короче срока или с ходом головки -
    по-прежнему незримая, слово владельца «если нет то ладно» для них в силе.
    """
    module = acceptance()
    warm = module.Ctx(
        "http://example", StallPage([179.13], [False], [True], 0.3), True, Path("/tmp"), {}
    )
    assert module._wait_stalls(warm, 0) == ([179.13], 179.13, [])
    mixed = module.Ctx(
        "http://example",
        StallPage([0.2, 0.7, 19.085], [False, False, False], [True, False, True], 0.3),
        True,
        Path("/tmp"),
        {},
    )
    waits, total, unseen = module._wait_stalls(mixed, 0)
    assert waits == [19.085]
    assert total == pytest.approx(19.085)
    assert unseen == [0.2, 0.7]


def test_сумма_подгрузов_на_заглушке_берёт_только_заминки_со_спиннером_в_кадре() -> None:
    """Про арифметику ``_wait_stalls``, и только про неё.

    Подгруз - заминка, у которой счётчик отметил спиннер в кадре (``seen``). Заминка без
    отметки уходит в третье число, а не в приговор; нули отбрасываются, как и прежде.
    Заминка, флага которой в снимке нет вовсе, в подгрузы не записывается молча: у неё
    просто нет доказательства спиннера. Поведение самого ``_METER_JS`` - ниже, браузером.
    """
    module = acceptance()
    clean = module.Ctx("http://example", StallPage([], []), True, Path("/tmp"), {})
    mixed = module.Ctx(
        "http://example",
        StallPage([0.4, 0.0, 0.03, 1.25, 0.7], [True, True, False, True]),
        True,
        Path("/tmp"),
        {},
    )

    assert module._wait_stalls(clean, 0) == ([], 0, [])
    waits, total, unseen = module._wait_stalls(mixed, 0)
    assert waits == [0.4, 1.25]
    assert total == pytest.approx(1.65)
    assert unseen == [0.03, 0.7]


#: Страница-пустышка счётчика: настоящий ``<video>``, который настоящим образом рисует
#: кадры. Картинка берётся с холста (``captureStream``), а не из файла, потому что
#: ``requestVideoFrameCallback`` внутри ``_METER_JS`` обязан сработать по-настоящему: без
#: первого кадра счётчик подгрузы не считает вовсе (``if (meter.frame !== null)``).
#:
#: 🔴 Тело завёрнуто в свою область видимости не для красоты. ``set_content`` меняет
#: документ, но НЕ окно: второй заход объявлял бы те же ``const`` в том же глобальном
#: лексическом окружении, весь скрипт падал бы с ошибкой ещё до ``srcObject``, и видео
#: второй страницы оставалось бы с ``readyState 0``. Кадра нет, счётчик молчит, а тест
#: краснеет на пустышке вместо предмета.
_STUB_VIDEO_PAGE = """<!doctype html><meta charset="utf-8">
<body><video id="v" muted playsinline autoplay></video><script>
(() => {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 32;
  const paint = canvas.getContext('2d');
  let tick = 0;
  setInterval(() => {
    tick = (tick + 32) % 256;
    paint.fillStyle = `rgb(${tick},${255 - tick},128)`;
    paint.fillRect(0, 0, 32, 32);
  }, 40);
  const video = document.getElementById('v');
  // Срок плеера до спиннера, как в продукте (`player.js`, ``STALL_SHOW_MS``): по нему
  // счётчик судит замирание без спиннера.
  window.TCPlayer = { STALL_SHOW_MS: 300 };
  // Спиннер ставится и снимается ровно как в продукте (`player.js`: обработчики `waiting`
  // и `playing` навешаны до счётчика, узел `.tc-spinner` вставляется синхронно), а
  // ``window.__stubQuiet`` выключает его, как плашка отсчёта выключает его в продукте, а
  // ``window.__stubHide`` дописывает к его стилю правило, прячущее уже вставленный узел.
  video.addEventListener('waiting', () => {
    if (window.__stubQuiet) return;
    const spinner = document.createElement('div');
    spinner.className = 'tc-spinner';
    spinner.style.cssText = 'width:40px;height:40px;background:#fff;' + (window.__stubHide || '');
    document.body.append(spinner);
  });
  video.addEventListener('playing', () => document.querySelectorAll('.tc-spinner')
    .forEach((node) => node.remove()));
  video.srcObject = canvas.captureStream(25);
  video.play();
})();
</script></body>"""

#: Развести ``waiting`` и ``playing`` руками, с настоящими паузами между ними.
_DRIVE_STALLS = """async (pauses) => {
  const video = document.querySelector('video');
  const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
  for (const ms of pauses) {
    video.dispatchEvent(new Event('waiting'));
    await sleep(ms);
    video.dispatchEvent(new Event('playing'));
  }
}"""

#: Заминки, которых зритель не видит: без спиннера (как под плашкой отсчёта) на 400 мс и
#: со спиннером, вставленным и снятым в одном тике, то есть не попавшим ни в один кадр.
#: Тик второй занят на 50 мс нарочно: без этого часы ``performance.now()`` (они огрублены)
#: давали бы нулевую длительность, и заминку отбрасывал бы ноль, а не правило спиннера.
#: Ещё три заминки по 200 мс (дюжина кадров) держат узел ``.tc-spinner`` в документе, но
#: скрытым: ``opacity:0``, ``display:none`` и нулевой размер. Узел есть, зритель его не видит.
_DRIVE_UNSEEN = """async () => {
  const video = document.querySelector('video');
  window.__stubQuiet = true;
  video.dispatchEvent(new Event('waiting'));
  await new Promise((done) => setTimeout(done, 400));
  video.dispatchEvent(new Event('playing'));
  window.__stubQuiet = false;
  video.dispatchEvent(new Event('waiting'));
  const busy = performance.now() + 50;
  while (performance.now() < busy) { /* главный поток занят: кадра нет */ }
  video.dispatchEvent(new Event('playing'));
  for (const hide of ['opacity:0', 'display:none', 'width:0;height:0']) {
    window.__stubHide = hide;
    video.dispatchEvent(new Event('waiting'));
    await new Promise((done) => setTimeout(done, 200));
    video.dispatchEvent(new Event('playing'));
  }
  window.__stubHide = '';
}"""

#: Замирание без спиннера: плёнка на паузе (головка стоит, у потока с холста буфера впереди
#: нет), ``waiting`` без спиннера, как в тепло-2 на стенде, и ход снова через 800 мс.
_DRIVE_FROZEN = """async () => {
  const video = document.querySelector('video');
  window.__stubQuiet = true;
  video.pause();
  video.dispatchEvent(new Event('waiting'));
  await new Promise((done) => setTimeout(done, 800));
  window.__stubQuiet = false;
  await video.play();
  await new Promise((done) => setTimeout(done, 100));
}"""

#: Незримых заминок в ``_DRIVE_UNSEEN``: без спиннера, без кадра и три скрытых.
_UNSEEN_COUNT = 5
#: Из них тех, где узел ``.tc-spinner`` стоит в документе хотя бы один кадр, но скрыт.
_HIDDEN_COUNT = 3

#: Допуск на замер подгруза в браузере. Счётчик берёт время из ``performance.now()``, а
#: паузы ставит ``setTimeout``: тот просыпается не раньше срока, но и не ровно в срок, и
#: на занятой машине опаздывает. 0.2 с - запас, при котором 0.4 и 1.25 всё ещё
#: различимы между собой и с нулём, то есть проверка не теряет смысла.
_STALL_TOLERANCE = 0.2


def _meter_over_stub(
    page: Any,
    module: ModuleType,
    meter_js: str,
    pauses: list[int],
    unseen: bool = False,
    frozen: bool = False,
) -> list[float]:
    """Прогнать счётчик над страницей-пустышкой и вернуть, что он насчитал подгрузами."""
    page.set_content(_STUB_VIDEO_PAGE)
    page.evaluate(meter_js)
    # Без первого кадра счётчик молчит по устройству, и ждать его надо честно.
    page.wait_for_function(
        "() => window.__tcAcceptanceMeter && window.__tcAcceptanceMeter.frame !== null",
        timeout=15000,
    )
    if unseen:
        page.evaluate(_DRIVE_UNSEEN)
    if frozen:
        page.evaluate(_DRIVE_FROZEN)
    if pauses:
        page.evaluate(_DRIVE_STALLS, pauses)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})
    return list(module._wait_stalls(ctx, 0)[0])


@pytest.mark.machine
def test_счётчик_подгрузов_в_настоящем_браузере_считает_разведённые_события() -> None:
    """``_METER_JS`` исполняется Chromium, а не проверяется грепом по своему исходнику.

    Щуп ставится отдельно от гейта (``pyproject.toml``: playwright в венв гейта не
    входит), поэтому без него проверка пропускается С НАЗВАННОЙ ПРИЧИНОЙ. Там, где
    браузер есть, она гоняется целиком, включая две отрицательные пробы: со снятым
    обработчиком ``waiting`` тот же прогон обязан дать пустой список, а счётчик старого
    правила («подгруз - любая заминка > 0») обязан записать в подгрузы и заминки, спиннера
    которых зритель не видел. Третья проба - счётчик, которому хватает узла с классом:
    он обязан взять заминки со скрытым спиннером. Новое правило их не берёт (слово
    владельца 20-09-2026: «если на приемнике есть спинер то это подгруз если нет то ладно»).
    """
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright ставится рядом с браузером (см. pyproject.toml), в венве гейта его нет",
    )
    module = acceptance()
    # Тот же обход, что у самого прибора: Chromium может лежать не в кэше playwright.
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "") or None
    with sync_api.sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page()
        try:
            none = _meter_over_stub(page, module, module._METER_JS, [])
            two = _meter_over_stub(page, module, module._METER_JS, [400, 1250], unseen=True)
            # Старое правило строкой из настоящего ``_METER_JS``: флаг «спиннер в кадре»
            # ставится всякой заминке, то есть подгрузом снова считается любая > 0.
            any_wait = module._METER_JS.replace(
                "meter.seen.push(meter.shown)", "meter.seen.push(true)"
            )
            assert any_wait != module._METER_JS
            old_rule = _meter_over_stub(page, module, any_wait, [400, 1250], unseen=True)
            # Видимость подменена на «есть узел с классом»: скрытый спиннер снова подгруз.
            node_only = module._METER_JS.replace(
                module._SPINNER_SEEN_JS, "() => document.querySelectorAll('.tc-spinner').length > 0"
            )
            # Проверки «подмена легла» тут нет нарочно: не легла - ``by_node`` ниже даст 2
            # вместо 5 и покраснеет на поведении, а не на строке исходника.
            by_node = _meter_over_stub(page, module, node_only, [400, 1250], unseen=True)
            # Отрицательная проба: обработчик не навешивается вовсе (снятие через
            # `removeEventListener` со свежей стрелкой - законный пустой вызов).
            stripped = module._METER_JS.replace(
                "video.addEventListener('waiting'", "video.removeEventListener('waiting'"
            )
            assert stripped != module._METER_JS
            blind = _meter_over_stub(page, module, stripped, [400, 1250])
            # Замирание без спиннера при пустом буфере - подгруз (решение оркестратора
            # 02-10-2026). Без флага ``frozen`` счётчик снова отдал бы его в незримые.
            still = _meter_over_stub(page, module, module._METER_JS, [], frozen=True)
            unfrozen = module._METER_JS.replace(
                "meter.frozen.push(meter.stuck)", "meter.frozen.push(false)"
            )
            missed = _meter_over_stub(page, module, unfrozen, [], frozen=True)
        finally:
            browser.close()

    assert none == []
    assert len(two) == 2, f"счётчик насчитал {two}"
    assert two[0] == pytest.approx(0.4, abs=_STALL_TOLERANCE)
    assert two[1] == pytest.approx(1.25, abs=_STALL_TOLERANCE)
    assert len(old_rule) == 2 + _UNSEEN_COUNT, (
        f"старое правило обязано взять и незримые заминки: {old_rule}"
    )
    assert len(by_node) == 2 + _HIDDEN_COUNT, (
        f"счётчик по узлу с классом обязан взять скрытый спиннер: {by_node}"
    )
    assert blind == []
    assert len(still) == 1, f"замирание без спиннера обязано стать подгрузом: {still}"
    assert still[0] == pytest.approx(0.8, abs=_STALL_TOLERANCE)
    assert unfrozen != module._METER_JS
    assert missed == []


def _meter_over_transition(page: Any, module: ModuleType, meter_js: str) -> tuple[Any, Any]:
    """Вооружить счётчик, подать подгруз, затем сменить серию на том же HLS-адресе.

    Возвращает ``(stale, real)``: ``stale`` - что счётчик записал в ``nextFrame`` после
    подгруза без смены адреса (хвост ЕЩЁ старой серии), ``real`` - после настоящей смены
    второй серии. Живой автопереход оставляет HLS-адрес прежним, но после ``ended``
    очищает и заново загружает тот же `<video>`; синтетика воспроизводит именно это.
    """
    page.set_content(_STUB_VIDEO_PAGE)
    page.evaluate(meter_js)
    page.wait_for_function(
        "() => window.__tcAcceptanceMeter && window.__tcAcceptanceMeter.frame !== null",
        timeout=15000,
    )
    page.evaluate("() => window.__tcAcceptanceMeter.arm()")
    page.evaluate(_DRIVE_STALLS, [250])
    # rVFC ставит кадр не в тот же тик, что событие ``playing``: даём ему тот же срок,
    # что и настоящему переходу ниже, иначе наивная версия читалась бы как починенная
    # просто потому, что кадр после подгруза ещё не успел прийти.
    with contextlib.suppress(Exception):
        page.wait_for_function("() => window.__tcAcceptanceMeter.nextFrame !== null", timeout=1000)
    stale = page.evaluate("() => window.__tcAcceptanceMeter.nextFrame")
    page.evaluate("""() => {
      const video = document.querySelector('video');
      video.dispatchEvent(new Event('ended'));
      video.dispatchEvent(new Event('emptied'));
      video.dispatchEvent(new Event('loadeddata'));
    }""")
    page.evaluate(_DRIVE_STALLS, [250])
    with contextlib.suppress(Exception):
        page.wait_for_function("() => window.__tcAcceptanceMeter.nextFrame !== null", timeout=3000)
    real = page.evaluate("() => window.__tcAcceptanceMeter.nextFrame")
    return stale, real


@pytest.mark.machine
def test_автопереход_видит_новую_серию_на_том_же_адресе_потока() -> None:
    """Хвост старой серии не сходит за кадр следующей, одинаковый URL не мешает замеру.

    ``_METER_JS`` до правки принимал ЛЮБОЙ ``playing`` после ``arm()`` - вооружение
    ставится, пока старая серия ещё играет (`web-acceptance.py:2280`), и подгруз на её
    хвосте (`waiting -> playing`) сам по себе выглядел точь-в-точь как переход. Наивная
    версия ниже воссоздаёт сломанный код без проверки новой загрузки - тем же приёмом,
    каким выше устроена `stripped`: строкой из настоящего ``_METER_JS``.
    """
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright ставится рядом с браузером (см. pyproject.toml), в венве гейта его нет",
    )
    module = acceptance()
    naive = module._METER_JS.replace(
        "meter.nextLoaded !== null && meter.nextPlaying === null",
        "meter.nextPlaying === null",
    )
    assert naive != module._METER_JS
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "") or None
    with sync_api.sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page()
        try:
            naive_stale, naive_real = _meter_over_transition(page, module, naive)
            fixed_stale, fixed_real = _meter_over_transition(page, module, module._METER_JS)
        finally:
            browser.close()

    assert isinstance(naive_stale, int | float), (
        f"сломанный счётчик обязан принять хвост старой серии как переход, взял {naive_stale!r}"
    )
    assert isinstance(naive_real, int | float)
    assert fixed_stale is None, (
        f"починенный счётчик принял хвост старой серии за переход: nextFrame={fixed_stale!r}"
    )
    assert isinstance(fixed_real, int | float), (
        f"починенный счётчик обязан дождаться кадра НОВОЙ серии, взял {fixed_real!r}"
    )


def _write_trace(directory: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    # Оборванный хвост ленты законен: писатель - демон, и последняя запись обрывается
    # вместе с погашенным показом. Прибор обязан читать ленту и с таким хвостом.
    (directory / "trace-20260916.jsonl").write_text(
        "\n".join([*lines, '{"at": 1, "event": "обор']), encoding="utf-8"
    )


def _astray(at: float, slot: int = 0) -> dict[str, Any]:
    return {
        "at": at,
        "phase": "timeline",
        "event": "нарезка разошлась с манифестом",
        "слот": slot,
        "расхождение": 1.82,
    }


def test_след_судит_только_окно_своего_прогона(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Чужой показ соседа по стенду лежит в той же ленте и нашим приговором быть не может."""
    module = acceptance()
    # Ждать хвост фонового писателя тут нечего: лента уже лежит на диске целиком.
    monkeypatch.setattr(module, "_TRACE_SETTLE", 0.0)
    since = time.time()
    _write_trace(tmp_path, [_astray(since - 600.0, slot=7), _astray(since + 30.0, slot=3)])
    ctx = module.Ctx("http://example", Page({}, 0.0), True, Path("/tmp"), {})

    result = module.check_41_astray(ctx, str(tmp_path), since)

    assert result.ok is False
    assert "«нарезка разошлась с манифестом» 1" in result.detail
    assert "слот 3 расхождение 1.82 с" in result.detail
    assert "слот 7" not in result.detail


def test_след_без_разъездов_зелёный_и_называет_число(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = acceptance()
    monkeypatch.setattr(module, "_TRACE_SETTLE", 0.0)
    since = time.time()
    _write_trace(tmp_path, [_astray(since - 600.0)])
    ctx = module.Ctx("http://example", Page({}, 0.0), True, Path("/tmp"), {})

    result = module.check_41_astray(ctx, str(tmp_path), since)

    assert result.ok is True
    assert "«нарезка разошлась с манифестом» 0" in result.detail
    assert "склейка не вышла: 0" in result.detail


def test_след_без_каталога_заблокирован_а_не_зелёный() -> None:
    """Прибор, которому ленту не назвали, обязан сказать это, а не промолчать зеленью."""
    module = acceptance()
    ctx = module.Ctx("http://example", Page({}, 0.0), True, Path("/tmp"), {})

    result = module.check_41_astray(ctx, "", time.time())

    assert result.ok is False
    assert result.blocked == "след стенда не назван (--trace-dir)"


def test_след_без_показа_заблокирован(tmp_path: Path) -> None:
    module = acceptance()
    ctx = module.Ctx("http://example", Page({}, 0.0), False, Path("/tmp"), {})

    result = module.check_41_astray(ctx, str(tmp_path), time.time())

    assert result.ok is False
    assert result.blocked is not None and "--play" in result.blocked


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

    clicked, waited, detail = module._click_play(ctx, 0)

    assert clicked is None
    assert waited >= 0.0
    assert detail.startswith("кнопка показа не появилась за ")


class SlowPlay(Video):
    """Кнопка, которая появляется только через ``delay`` секунд игрушечных часов."""

    def __init__(self, page: SlowPlayPage, delay: float) -> None:
        super().__init__(0)
        self.page, self.delay = page, delay

    @property
    def first(self) -> SlowPlay:
        return self

    def wait_for(self, **_: Any) -> None:
        self.page.clock += self.delay

    def click(self) -> None:
        return None


class SlowPlayPage(Page):
    def __init__(self, delay: float) -> None:
        super().__init__({}, 0.0)
        self.clock = 0.0
        self.delay = delay

    def locator(self, selector: str) -> Video:
        assert selector == "[data-tc-play]"
        return SlowPlay(self, self.delay)


def test_медленная_кнопка_показа_возвращает_своё_ожидание(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Число ожидания - предмет приговора пп. 4 и 5, а не побочная запись в строке."""
    module = acceptance()
    page = SlowPlayPage(27.4)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: page.clock))
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})

    clicked, waited, detail = module._click_play(ctx)

    assert clicked == 27.4
    assert waited == pytest.approx(27.4)
    assert detail == ""
    # Порог берётся из цели зрителя, а не из того, что показал стенд: 27.4 с его
    # перескакивают, и пункт обязан на этом краснеть.
    assert waited > module._PLAY_READY_BAR


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


#: Сэмпл пробы курсора: класс на ``<html>``, вычисленный курсор под точкой мыши, над
#: контрольным узлом и на корне, прозрачность верха и низа панели плеера (нет - None).
def _cursor_sample(
    t: float, cls: bool, cursor: str, top: float | None = None, bottom: float | None = None
) -> dict[str, Any]:
    return {
        "t": t,
        "cls": cls,
        "at": cursor,
        "ctl": cursor,
        "root": cursor,
        "top": top,
        "bottom": bottom,
    }


def _cursor_marks(key_at: float, move2_at: float, move1_at: float = 0.0) -> list[dict[str, Any]]:
    return [
        {"t": move1_at, "kind": "move"},
        {"t": key_at, "kind": "key"},
        {"t": move2_at, "kind": "move"},
    ]


def _healthy_cursor_log(with_panel: bool) -> dict[str, Any]:
    """Живой след сценария: движение, клавиша, движение, покой 10 с.

    Панель ходит теми же мигами, что и класс, переходами по 0.4 с: 600 мс после
    первого движения и секунда после возврата оставляют её оседлевшей в 1 к моментам,
    где честный якорь :func:`_panel_cross` обязан её такой увидеть.
    """
    samples = [
        # после первого движения панель поднялась и стоит в 1, курсор виден
        _cursor_sample(60.0, False, "pointer", 1.0, 1.0),
        _cursor_sample(560.0, False, "pointer", 1.0, 1.0),
        # клавиша в 600: скрыта следующим сэмплом, панель пошла вниз одновременно
        _cursor_sample(612.0, True, "none", 0.94, 0.94),
        _cursor_sample(800.0, True, "none", 0.5, 0.5),
        _cursor_sample(1000.0, True, "none", 0.0, 0.0),
        # движение в 1200: курсор вернулся, панель пошла вверх одновременно
        _cursor_sample(1212.0, False, "pointer", 0.06, 0.06),
        _cursor_sample(1400.0, False, "pointer", 0.5, 0.5),
        _cursor_sample(2200.0, False, "pointer", 1.0, 1.0),
        # покой: на 5 с ещё видна, ушла на 10-й
        _cursor_sample(5000.0, False, "pointer", 1.0, 1.0),
        _cursor_sample(6200.0, False, "pointer", 1.0, 1.0),
        _cursor_sample(11212.0, True, "none", 0.94, 0.94),
        _cursor_sample(11400.0, True, "none", 0.4, 0.4),
        _cursor_sample(12200.0, True, "none", 0.0, 0.0),
    ]
    if not with_panel:
        for sample in samples:
            sample["top"] = sample["bottom"] = None
    return {"samples": samples, "marks": _cursor_marks(600.0, 1200.0)}


def test_курсор_живой_след_зелёный_и_называет_числа() -> None:
    module = acceptance()

    plain, plain_ok = module._cursor_rows("главная", _healthy_cursor_log(False))
    shown, shown_ok = module._cursor_rows("показ", _healthy_cursor_log(True))

    assert plain_ok and shown_ok
    assert plain == ["главная: покой 10012, клавиша 12, движение 12; на 5.0 с ещё виден"]
    assert shown == [
        "показ: покой 10012, клавиша 12, движение 12; на 5.0 с ещё виден; "
        "панель Δверх 0, Δниз 0, Δверх 0, Δниз 0, Δверх 0, Δниз 0"
    ]


@pytest.mark.parametrize(
    "broken",
    (
        # клавиша вовсе не прячет: слушателя нет
        "no_key",
        # покой 3 с - прежнее поведение плеера до TC-1319
        "short_idle",
        # курсор над контрольным узлом не скрылся: CSS-запрет потерян, класс один
        "css_lost",
        # панель опаздывает на 400 мс - «в одном миге» больше нет
        "panel_late",
    ),
)
def test_курсор_краснеет_на_каждой_поломке_отдельно(broken: str) -> None:
    module = acceptance()
    log = _healthy_cursor_log(True)
    samples = log["samples"]
    if broken == "no_key":
        for sample in samples:
            if 612.0 <= sample["t"] <= 1000.0:
                sample["cls"] = False
                sample["at"] = sample["ctl"] = sample["root"] = "pointer"
                sample["top"] = sample["bottom"] = 1.0
    elif broken == "short_idle":
        for sample in samples:
            if sample["t"] >= 11212.0:
                sample["t"] -= 6400.0
            elif sample["t"] >= 5000.0:
                sample["cls"] = True
                sample["at"] = sample["ctl"] = sample["root"] = "none"
                sample["top"] = sample["bottom"] = 0.0
    elif broken == "css_lost":
        for sample in samples:
            if sample["cls"]:
                sample["ctl"] = "pointer"
    else:
        late: list[dict[str, Any]] = []
        for sample in samples:
            if sample["cls"]:
                sample["top"] = sample["bottom"] = 1.0
                late.append({**sample, "t": sample["t"] + 400.0, "top": 0.94, "bottom": 0.94})
        samples.extend(late)
        samples.sort(key=lambda sample: sample["t"])

    rows, ok = module._cursor_rows("показ", log)

    assert not ok, rows[0]
    assert len(rows) > 1, "претензия обязана попасть в таблицу, а не остаться в приговоре"


def test_курсор_без_пробы_называет_чего_не_хватает() -> None:
    module = acceptance()

    rows, ok = module._cursor_rows("главная", {"samples": [], "marks": []})

    assert not ok
    assert rows == ["главная: проба не собрала сэмплов"]


def test_показ_гасит_свой_показ_даже_без_кадра(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пункт 4 не гасил свой показ, и следующий пункт стартовал поверх идущего."""
    module = acceptance()
    log: list[str] = []
    page = SimpleNamespace(evaluate=lambda *_a: None)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})
    monkeypatch.setattr(module, "_playback_guard", lambda *_args: None)
    monkeypatch.setattr(module, "_open_card_by_page", lambda *_args: None)
    monkeypatch.setattr(module, "_card_key", lambda _ctx: "key")

    def click(_ctx: Any) -> tuple[float, float, str]:
        log.append("клик")
        return 1.0, 0.5, ""

    monkeypatch.setattr(module, "_click_play", click)
    monkeypatch.setattr(module, "_frame_measure", lambda *_args: (None, {}))
    monkeypatch.setattr(module, "_overlay_text", lambda _ctx: "")
    monkeypatch.setattr(module, "_stop_show", lambda _ctx: log.append("стоп"))

    result = module.check_4_playback(ctx)

    assert not result.ok
    assert log == ["клик", "стоп"]


def _card_29(monkeypatch: pytest.MonkeyPatch, states: list[dict[str, Any]], named: str) -> Any:
    """Пункт 29 с карточкой ``named``: ``/api/state`` отвечает по очереди ``states``."""
    module = acceptance()
    button = SimpleNamespace(
        first=SimpleNamespace(
            wait_for=lambda **_k: None, is_visible=lambda: True, click=lambda: None
        ),
        count=lambda: 1,
    )
    page = SimpleNamespace(locator=lambda *_a, **_k: button, wait_for_timeout=lambda _ms: None)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {"web.detail.play_on_tv": "TV"})
    answers = iter(states)
    last: list[dict[str, Any]] = [{}]

    def state(_ctx: Any) -> dict[str, Any]:
        last[0] = next(answers, last[0])
        return last[0]

    monkeypatch.setattr(module, "_open_card_by_page", lambda *_args: None)
    monkeypatch.setattr(module, "_shot", lambda *_args: None)
    monkeypatch.setattr(module, "_state", state)
    monkeypatch.setattr(module, "_stop_show", lambda _ctx: None)
    monkeypatch.setattr(module, "_card_texts", lambda _ctx: {"title": named})
    monkeypatch.setattr(module, "_tv_text", lambda _ctx: "")
    monkeypatch.setattr(module, "_position", lambda _ctx: 5.0)
    monkeypatch.setattr(module, "_await_position_growth", lambda *_args: (True, 15.0))
    monkeypatch.setattr(module, "_post", lambda *_args: (200, b"{}"))
    return module.check_29_card_tv_button(ctx)


def test_кнопка_на_тв_не_принимает_чужой_показ(monkeypatch: pytest.MonkeyPatch) -> None:
    """Играет не картина карточки - красный, хотя состояние ``playing`` и позиция растёт."""
    playing = {"state": "playing", "title": "Rick and Morty", "tv": "tv"}
    result = _card_29(monkeypatch, [{"state": "idle"}, {"state": "idle"}, playing], "Interstellar")

    assert not result.ok
    assert "НЕ ТА КАРТИНА" in result.detail


def test_кнопка_на_тв_не_нажимается_поверх_идущего_показа(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playing = {"state": "playing", "title": "Interstellar", "tv": "tv"}
    result = _card_29(monkeypatch, [playing, playing, playing], "Interstellar")

    assert not result.ok
    assert "до клика уже идёт показ" in result.detail


def test_кнопка_на_тв_зелёная_на_своей_картине(monkeypatch: pytest.MonkeyPatch) -> None:
    playing = {"state": "playing", "title": "Interstellar", "tv": "tv"}
    result = _card_29(monkeypatch, [{"state": "idle"}, {"state": "idle"}, playing], "Interstellar")

    assert result.ok, result.detail
    assert "до клика 'idle'" in result.detail


def test_серия_по_api_state_ждёт_выбранную_а_не_прошлый_показ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Прошлый прогон оставил играть s2e2: первый опрос после клика по s2e1 видит его."""
    module = acceptance()
    answers = iter([(200, b'{"season": 2, "episode": 2}'), (200, b'{"season": 2, "episode": 1}')])
    monkeypatch.setattr(module, "_get", lambda _url: next(answers))
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    ctx = module.Ctx("http://example", SimpleNamespace(), True, Path("/tmp"), {})

    assert module._await_episode(ctx, (2, 1)) == (2, 1)


@pytest.mark.parametrize(("step", "rate"), [(2.0, 1.0), (0.25, 1.0)])
def test_доклад_который_продукт_досчитывает_сам_не_ждёт_пяти_секунд(
    monkeypatch: pytest.MonkeyPatch, step: float, rate: float
) -> None:
    """Досчёт продукта меняет доклад каждый опрос каста или каждый запрос: 5 с он не живёт."""
    module = acceptance()
    clock = [0.0]

    def report(_ctx: Any) -> tuple[float, str, str]:
        return 100.0 + rate * step * int(clock[0] // step), "playing", ""

    def wait(ms: int) -> None:
        clock[0] += ms / 1000.0

    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module, "_box_at", lambda _ctx: (0.0, True, ""))
    monkeypatch.setattr(module, "_receiver_report", report)
    page = SimpleNamespace(wait_for_timeout=wait)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})

    at, changed, word, problem = module._await_stale_receiver_report(ctx)

    assert (word, problem) == ("playing", "")
    assert at is not None and changed is not None
    assert clock[0] < 4 * step + 1.0
