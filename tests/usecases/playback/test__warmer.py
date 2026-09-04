"""Зеркало сборки прогрева: одно решение о кодировании у показа и у прогрева."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import torrcast.adapters.recode.encode as encode_module
import torrcast.domain.version as version_module
from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.recode.whole_encode import whole_encode
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.usecases.playback._warmer import _warmer
from torrcast.usecases.warm.settings import META
from torrcast.usecases.warm.warm_key import warm_key


@pytest.fixture(autouse=True)
def _tract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карта опорных кадров - готовая; решение о кодировании считают настоящие классы."""


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
        self.plans: list[tuple[tuple[int, ...], str, float]] = []

    def plan(
        self, pack: str, warm: str, spots: tuple[int, ...], preset: str = "", mbit: float = 0.0
    ) -> None:
        self.plans.append((spots, preset, mbit))


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

    assert noted.plans == [(recoder.targets, "ultrafast", 9.0)]


def test_without_any_recode_the_plan_stays_empty(tmp_path: Path) -> None:
    """Ни сплошного, ни точечного перекода - в записи пустой пресет и нулевой битрейт."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    noted = _Noted()
    install(noted)
    try:
        _warmer(config, "http://ts", 0, grid(), 0.0, "кино")
    finally:
        install(Silent())

    assert noted.plans == [((), "", 0.0)]


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


def test_a_piece_above_the_receivers_cap_is_removed_before_the_show_reads_it(
    tmp_path: Path,
) -> None:
    """Невыдаваемая копия не занимает бюджет и не доживает до пути показа."""
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    lines = grid()
    where = tmp_path / "warm" / warm_key("http://ts", 0, lines)
    where.mkdir(parents=True)
    piece = where / "v1.ts"
    piece.write_bytes(b"x" * (CAUTIOUS.max_segment_bytes + 1))

    made = _warmer(config, "http://ts", 0, lines, 0.0, "кино")

    assert made is not None
    assert not piece.exists(), "невыдаваемый кусок остался занимать бюджет"


def test_a_heavy_copy_under_a_spot_recode_survives_the_start_of_the_show(
    tmp_path: Path,
) -> None:
    """Копия тяжёлого места - работа прогрева впереди, и старт показа её не забирает.

    Замер на настоящем каталоге посреди прогрева («Дюна: Часть вторая», 1080p
    11.9 Мбит/с): 64 куска из 105 тяжелее осторожного потолка, 59 из них - цели
    точечного перекода. Не дойди слоты кодировщика до уборки, продолжение показа
    сносило бы их каждый вечер, а прогрев тянул бы их из роя заново.
    """
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    lines = grid()
    weights = Weights.of(film_keys(), lines)
    assert weights is not None
    recoder = Recoder(
        source="http://ts",
        audio=0,
        grid=lines,
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )
    assert recoder.targets, "стенду нужен показ, у которого точечный перекод есть"
    slot = recoder.targets[0]
    where = tmp_path / "warm" / warm_key("http://ts", 0, lines, None, recoder.targets)
    where.mkdir(parents=True)
    piece = where / f"v{slot}.ts"
    piece.write_bytes(b"x" * (CAUTIOUS.max_segment_bytes + 1))

    made = _warmer(config, "http://ts", 0, lines, 0.0, "кино", recoder=recoder)

    assert made is not None
    assert piece.exists(), "старт показа забрал копию, которую сам же собрался перекодировать"


def test_a_shelf_warmed_by_yesterdays_rules_is_not_served_after_the_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Правила кодирования поменялись - полка перестаёт находиться, и кусок собирается заново.

    Прежде это было не так: ключ каталога знал РЕШЕНИЕ (пресет, цель, кадр) и молчал о
    правилах, которыми решение разворачивается в команду. Снятый ``-level`` (TC-871)
    решения не тронул, ключа не сдвинул - и на любой машине, где полка уже прогрета,
    показ продолжал отдавать кусок с битым уровнем, пока полку не снесут руками.

    Вчерашние правила тут - буфер VBV в две секунды потолка, каким он и был до замера
    (:data:`torrcast.adapters.recode.encode_settings.VBV_SECONDS`): решение при этом до
    знака то же самое, а ``-bufsize`` в команде другой.
    """
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    lines = grid()
    whole = whole_encode(9.0)

    monkeypatch.setattr(encode_module, "VBV_SECONDS", 2.0)
    decided = (whole.preset, whole.mbit, whole.mark)
    yesterday = _warmer(config, "http://ts", 0, lines, 0.0, "кино", whole=whole)
    assert yesterday is not None
    yesterday.vault.dir.mkdir(parents=True, exist_ok=True)
    yesterday.vault.path(1).write_bytes(b"piece built by yesterday rules")
    assert yesterday.vault.have(1), "стенд не собрался: вчерашнего куска на полке нет"

    monkeypatch.undo()
    today = _warmer(config, "http://ts", 0, lines, 0.0, "кино", whole=whole)

    assert today is not None
    # Случай ловится ровно правилами, а не чужой причиной: решение до знака прежнее.
    assert (whole.preset, whole.mbit, whole.mark) == decided, "поехало решение - случай не тот"
    assert today.vault.dir != yesterday.vault.dir, "ключ не заметил правки правил кодирования"
    assert not today.vault.have(1), "показ отдаёт кусок, собранный вчерашними правилами"


def test_a_spot_recode_shelf_is_not_served_after_the_rules_changed_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """То же и на ТОЧЕЧНОМ пути - том самом, на котором ``-level`` и убивал показ.

    Решения точечного перекода в ``encode`` нет вовсе: в ключ от него идут одни номера
    слотов. Спроси ключ отпечаток только у сплошного перекода - правка правил проехала бы
    мимо ровно того пути, ради которого её и делали.
    """
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    lines = grid()
    weights = Weights.of(film_keys(), lines)
    assert weights is not None
    recoder = Recoder(
        source="http://ts",
        audio=0,
        grid=lines,
        spare=tmp_path / "recode",
        weights=weights,
        threshold=0.0,
        encode=Encode(preset="ultrafast", mbit=9.0),
    )
    assert recoder.targets, "стенду нужен показ, у которого точечный перекод есть"
    slot = recoder.targets[0]

    monkeypatch.setattr(encode_module, "VBV_SECONDS", 2.0)
    yesterday = _warmer(config, "http://ts", 0, lines, 0.0, "кино", recoder=recoder)
    assert yesterday is not None
    yesterday.vault.dir.mkdir(parents=True, exist_ok=True)
    yesterday.vault.path(slot).write_bytes(b"spot piece built by yesterday rules")
    assert yesterday.vault.have(slot), "стенд не собрался: вчерашнего куска на полке нет"

    monkeypatch.undo()
    today = _warmer(config, "http://ts", 0, lines, 0.0, "кино", recoder=recoder)

    assert today is not None
    assert not today.vault.have(slot), "точечный кусок вчерашних правил дожил до выдачи"


def test_an_update_that_left_the_encoding_rules_alone_keeps_the_warm_shelf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Правила те же - вся полка остаётся на месте: цена лечения не выше болезни.

    Обновление тут настоящее: продукт уехал на другую версию, правил кодирования не
    тронув. Подмешай ключ версию (первый путь карточки), и каждый выпуск отправлял бы
    уже прогретый фильм греться заново - лечение дороже болезни. Мера - число попаданий:
    сколько кусков полка отдавала до обновления, столько же обязана отдавать и после.
    """
    config = Config(warm=True, warm_dir=str(tmp_path / "warm"))
    lines = grid()
    whole = whole_encode(9.0)
    slots = range(lines.count)

    before = _warmer(config, "http://ts", 0, lines, 0.0, "кино", whole=whole)
    assert before is not None
    before.vault.dir.mkdir(parents=True, exist_ok=True)
    for slot in slots:
        before.vault.path(slot).write_bytes(b"warm piece")
    hits_before = sum(before.vault.have(slot) for slot in slots)

    monkeypatch.setattr(version_module, "__version__", "99.99.99")
    after = _warmer(config, "http://ts", 0, lines, 0.0, "кино", whole=whole)

    assert after is not None
    hits_after = sum(after.vault.have(slot) for slot in slots)
    assert hits_before == lines.count, "стенд не собрался: полка пуста ещё до обновления"
    assert after.vault.dir == before.vault.dir, "выпуск сам по себе увёл полку в другой каталог"
    assert hits_after == hits_before, "обновление без правки правил обесценило полку"
