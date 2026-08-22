"""Зеркало сборки прогрева: одно решение о кодировании у показа и у прогрева."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes import composition
from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.recode.whole_encode import whole_encode
from torrcast.domain.config import Config
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.usecases.playback._warmer import _warmer
from torrcast.usecases.warm.settings import META
from torrcast.usecases.warm.warm_key import warm_key


@pytest.fixture(autouse=True)
def _tract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карта опорных кадров - готовая; решение о кодировании считают настоящие классы."""
    composition.use_film_keys(monkeypatch, lambda source: film_keys())


def test_warming_switched_off_means_no_warmer_at_all(tmp_path: Path) -> None:
    """Прогрев выключен настройкой - собирать нечего."""
    config = Config(warm=False, warm_dir=str(tmp_path / "warm"))

    assert _warmer(config, "http://ts", 0, grid(), 0.0, "кино") is None


def test_the_whole_recode_leaves_no_spots_to_the_warmer(tmp_path: Path) -> None:
    """Файл едет сплошным перекодом - точечных слотов у прогрева нет и быть не может."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    whole = whole_encode(9.0)

    made = _warmer(config, "http://ts", 0, grid(), 0.0, "кино", whole=whole)

    assert made is not None
    assert made.encode is whole
    assert made.spots == (), "поверх сплошного перекода перекодировать нечего"


def test_the_spots_of_the_show_become_the_spots_of_the_warm_up(tmp_path: Path) -> None:
    """Тяжёлые куски греются ТЕМИ ЖЕ слотами и тем же решением, что берёт живой показ."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    recoder = Recoder(
        source="http://ts",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )

    made = _warmer(config, "http://ts", 0, grid(), 0.0, "кино", recoder=recoder)

    assert made is not None
    assert made.encode is None, "прогрев ушёл в сплошной перекод там, где показ отдаёт копию"
    assert made.spots == recoder.targets
    assert made.spot_encode is recoder.encode


def test_the_place_of_the_show_becomes_the_place_of_the_warm_up(tmp_path: Path) -> None:
    """Греют с того места, откуда смотрят: голова фильма - потом."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))

    made = _warmer(config, "http://ts", 0, grid(), 95.0, "кино")

    assert made is not None
    assert made.began_at == grid().slot_at(95.0)


class _Noted(Silent):
    """Молчащая лента, которая помнит одну запись плана кодирования."""

    def __init__(self) -> None:
        self.plans: list[tuple[str, float]] = []

    def plan(self, pack: str, warm: str, spots: int, preset: str = "", mbit: float = 0.0) -> None:
        self.plans.append((preset, mbit))


def test_the_plan_names_the_decision_the_spots_are_taken_with(tmp_path: Path) -> None:
    """Точечный перекод есть - в записи плана стоят ЕГО пресет и битрейт, а не чужие."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    weights = Weights.of(film_keys(), grid())
    assert weights is not None
    recoder = Recoder(
        source="http://ts",
        audio=0,
        grid=grid(),
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )
    noted = _Noted()
    install(noted)
    try:
        _warmer(config, "http://ts", 0, grid(), 0.0, "кино", recoder=recoder)
    finally:
        install(Silent())

    assert noted.plans == [("ultrafast", 9.0)]


def test_without_any_recode_the_plan_stays_empty(tmp_path: Path) -> None:
    """Ни сплошного, ни точечного перекода - в записи пустой пресет и нулевой битрейт."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    noted = _Noted()
    install(noted)
    try:
        _warmer(config, "http://ts", 0, grid(), 0.0, "кино")
    finally:
        install(Silent())

    assert noted.plans == [("", 0.0)]


def test_the_warm_catalogue_of_the_previous_way_is_relaid_before_the_show_reads_it(
    tmp_path: Path,
) -> None:
    """Каталог прежнего способа перекладывается ЕЩЁ ПРИ СБОРКЕ, до первого запроса сегмента.

    Показ читает прогретое раньше упаковки (:func:`torrcast.usecases.feed_pack.feed_segment._warm`),
    и та же лента отдаёт куски этого каталога. Останься помеченный кусок на диске - он уехал
    бы зрителю ровно тем, чем лежал.
    """
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    lines = grid()
    where = tmp_path / "warm" / warm_key("http://ts", 0, lines)
    where.mkdir(parents=True)
    (where / "v1.ts").write_bytes(b"old piece")
    (where / "v1.rec").touch()
    (where / "v2.ts").write_bytes(b"copy")
    (where / META).write_text(json.dumps({"key": "k", "at": 1.0}), encoding="utf-8")

    made = _warmer(config, "http://ts", 0, lines, 0.0, "кино")

    assert made is not None
    assert not (where / "v1.ts").exists(), "кусок прежнего способа дожил до выдачи"
    assert not (where / "v1.rec").exists()
    assert (where / "v2.ts").exists(), "копию переложили зря"
