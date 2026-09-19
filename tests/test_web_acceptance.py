"""Сторожа зрительских измерений ``web-acceptance.py`` без живого браузера."""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import json
import os
import sys
import time
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


def test_сумма_подгрузов_на_заглушке_считается_и_отбрасывает_нули() -> None:
    """Про арифметику ``_wait_stalls``, и только про неё.

    Прежде эта же проверка кончалась строкой ``"addEventListener('waiting'" in _METER_JS``
    и звалась проверкой счётчика. Счётчик она не проверяла: строка в исходнике не
    говорит ни что обработчик навешан, ни что он считает. Поведение самого ``_METER_JS``
    проверяется ниже настоящим браузером.
    """
    module = acceptance()
    clean = module.Ctx("http://example", StallPage([]), True, Path("/tmp"), {})
    broken = module.Ctx("http://example", StallPage([0.4, 0.0, 1.25]), True, Path("/tmp"), {})

    assert module._wait_stalls(clean, 0) == ([], 0)
    waits, total = module._wait_stalls(broken, 0)
    assert waits == [0.4, 1.25]
    assert total == pytest.approx(1.65)


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

#: Допуск на замер подгруза в браузере. Счётчик берёт время из ``performance.now()``, а
#: паузы ставит ``setTimeout``: тот просыпается не раньше срока, но и не ровно в срок, и
#: на занятой машине опаздывает. 0.2 с - запас, при котором 0.4 и 1.25 всё ещё
#: различимы между собой и с нулём, то есть проверка не теряет смысла.
_STALL_TOLERANCE = 0.2


def _meter_over_stub(
    page: Any, module: ModuleType, meter_js: str, pauses: list[int]
) -> list[float]:
    """Прогнать счётчик над страницей-пустышкой и вернуть, что он насчитал."""
    page.set_content(_STUB_VIDEO_PAGE)
    page.evaluate(meter_js)
    # Без первого кадра счётчик молчит по устройству, и ждать его надо честно.
    page.wait_for_function(
        "() => window.__tcAcceptanceMeter && window.__tcAcceptanceMeter.frame !== null",
        timeout=15000,
    )
    if pauses:
        page.evaluate(_DRIVE_STALLS, pauses)
    ctx = module.Ctx("http://example", page, True, Path("/tmp"), {})
    return list(module._wait_stalls(ctx, 0)[0])


@pytest.mark.machine
def test_счётчик_подгрузов_в_настоящем_браузере_считает_разведённые_события() -> None:
    """``_METER_JS`` исполняется Chromium, а не проверяется грепом по своему исходнику.

    Щуп ставится отдельно от гейта (``pyproject.toml``: playwright в венв гейта не
    входит), поэтому без него проверка пропускается С НАЗВАННОЙ ПРИЧИНОЙ. Там, где
    браузер есть, она гоняется целиком, включая отрицательную пробу: со снятым
    обработчиком ``waiting`` тот же прогон обязан дать пустой список.
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
            two = _meter_over_stub(page, module, module._METER_JS, [400, 1250])
            # Отрицательная проба: обработчик не навешивается вовсе (снятие через
            # `removeEventListener` со свежей стрелкой - законный пустой вызов).
            stripped = module._METER_JS.replace(
                "video.addEventListener('waiting'", "video.removeEventListener('waiting'"
            )
            assert stripped != module._METER_JS
            blind = _meter_over_stub(page, module, stripped, [400, 1250])
        finally:
            browser.close()

    assert none == []
    assert len(two) == 2, f"счётчик насчитал {two}"
    assert two[0] == pytest.approx(0.4, abs=_STALL_TOLERANCE)
    assert two[1] == pytest.approx(1.25, abs=_STALL_TOLERANCE)
    assert blind == []


def _meter_over_transition(page: Any, module: ModuleType, meter_js: str) -> tuple[Any, Any]:
    """Вооружить счётчик, подать подгруз на ТОМ ЖЕ адресе потока, затем сменить адрес.

    Возвращает ``(stale, real)``: ``stale`` - что счётчик записал в ``nextFrame`` после
    подгруза без смены адреса (хвост ЕЩЁ старой серии), ``real`` - после настоящей смены
    адреса (следующая серия). Живой автопереход роняет `<video>` на тот же элемент и
    рестартует упаковку у самого хвоста - подгруз там штатное дело (TC-1341), и синтетика
    тут воспроизводит именно эту пару событий, а не выдуманную форму.
    """
    page.set_content(_STUB_VIDEO_PAGE)
    page.evaluate(meter_js)
    page.wait_for_function(
        "() => window.__tcAcceptanceMeter && window.__tcAcceptanceMeter.frame !== null",
        timeout=15000,
    )
    page.evaluate("() => { window.TCPlayer = { _url: 'ep-1' }; window.__tcAcceptanceMeter.arm(); }")
    page.evaluate(_DRIVE_STALLS, [250])
    # rVFC ставит кадр не в тот же тик, что событие ``playing``: даём ему тот же срок,
    # что и настоящему переходу ниже, иначе наивная версия читалась бы как починенная
    # просто потому, что кадр после подгруза ещё не успел прийти.
    with contextlib.suppress(Exception):
        page.wait_for_function("() => window.__tcAcceptanceMeter.nextFrame !== null", timeout=1000)
    stale = page.evaluate("() => window.__tcAcceptanceMeter.nextFrame")
    page.evaluate("() => { window.TCPlayer._url = 'ep-2'; }")
    page.evaluate(_DRIVE_STALLS, [250])
    with contextlib.suppress(Exception):
        page.wait_for_function("() => window.__tcAcceptanceMeter.nextFrame !== null", timeout=3000)
    real = page.evaluate("() => window.__tcAcceptanceMeter.nextFrame")
    return stale, real


@pytest.mark.machine
def test_автопереход_не_принимает_playing_с_тем_же_адресом_потока() -> None:
    """TC-1341: хвост ЕЩЁ старой серии не сходит за первый кадр следующей.

    ``_METER_JS`` до правки принимал ЛЮБОЙ ``playing`` после ``arm()`` - вооружение
    ставится, пока старая серия ещё играет (`web-acceptance.py:2280`), и подгруз на её
    хвосте (`waiting -> playing`) сам по себе выглядел точь-в-точь как переход. Наивная
    версия ниже воссоздаёт ИМЕННО этот старый код (условие без сверки адреса) - тем же
    приёмом, каким выше устроена `stripped`: строкой из настоящего ``_METER_JS``, а не
    сочинённым текстом.
    """
    sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright ставится рядом с браузером (см. pyproject.toml), в венве гейта его нет",
    )
    module = acceptance()
    naive = module._METER_JS.replace(
        "meter.nextPlaying === null && stream() !== meter.armedStream) {",
        "meter.nextPlaying === null) {",
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
        f"наивный счётчик обязан принять хвост старой серии как переход, взял {naive_stale!r}"
    )
    assert isinstance(naive_real, int | float)
    assert fixed_stale is None, (
        f"починенный счётчик принял хвост старой серии за переход: nextFrame={fixed_stale!r}"
    )
    assert isinstance(fixed_real, int | float), (
        f"починенный счётчик обязан дождаться кадра НОВОГО адреса, взял {fixed_real!r}"
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
