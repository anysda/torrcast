"""Кончилась очередь: лучший из слабых роёв берётся, только если он живой под спросом."""

from dataclasses import replace
from typing import cast

import pytest

from tests.fakes import composition
from tests.usecases.select_bench.world import GB, RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.json_value import JsonValue
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench_tally import _Tally
from torrcast.usecases.select_bench._bench_weak import _weak_alive
from torrcast.usecases.select_bench.bench import Bench

MEDIA = Media(RUNTIME, (), "h264", height=1080, width=1920)
#: Отбор судит, а не пропускает: окно замера открыто сразу, и любой рой «короток».
PROFILE = replace(CAUTIOUS, supply_settle_seconds=0.0, supply_window_seconds=0.0, supply_ratio=10.0)


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские строки отбора."""


class _Stalled(Torrents):
    """На вехах прогрева счётчик стоит - 0.00; принятое под спросом копится в ``intake``."""

    intake = 0.0

    def status(self, torrent_hash: str) -> dict[str, JsonValue]:
        return {"bytes_read": self.intake}


def _resolve(monkeypatch: pytest.MonkeyPatch, speed: float, asked: list[tuple[str, int]]) -> int:
    torrents = _Stalled()

    def _demand(source: str, offset: int, seconds: float) -> None:
        asked.append((source, offset))
        torrents.intake += speed * seconds  # рой везёт ``speed`` байт в секунду

    composition.use_swarm_demand(monkeypatch, _demand)
    pool = [rel("one"), rel("two")]
    bench = Bench(torrents, prober=probes(pool, MEDIA, MEDIA), profile=PROFILE)
    return bench.resolve(plan(pool), Args(query=["кино"]), Said()).number


def test_a_swarm_dead_under_demand_is_not_taken(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-1291: вместо «беру (0.00x)» и вечного PREPARING - честный отказ."""
    with pytest.raises(NotFoundError, match=r"годного релиза нет \(1 - рой везёт 0.00"):
        _resolve(monkeypatch, 0.0, [])

    said = capsys.readouterr().out
    assert "беру (0.00x)" not in said
    assert "и под спросом везёт 0.00 при нужных" in said


def test_the_remeasure_reads_the_middle_of_the_film(monkeypatch: pytest.MonkeyPatch) -> None:
    """Голова уже в кэше: спрос настоящий только там, где не читал никто."""
    asked: list[tuple[str, int]] = []
    with pytest.raises(NotFoundError):
        _resolve(monkeypatch, 0.0, asked)

    assert asked == [("http://ts/hash-magnet-one/0", 2 * GB)]


def test_a_swarm_alive_under_demand_is_taken_with_the_new_numbers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ранний ноль бывает временным: ожил рой к концу очереди - его и показываем."""
    chosen = _resolve(monkeypatch, 1_500_000.0, [])

    assert chosen == 1
    assert "рой релиза 1 везёт 12.00 при нужных" in capsys.readouterr().out


def test_a_weak_swarm_above_the_floor_is_taken_without_a_remeasure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пол режет только мёртвых: 0.42x кадр довозит, лишние 4 с ему ни к чему."""

    def _demand(source: str, offset: int, seconds: float) -> None:
        raise AssertionError("выше пола перемер не нужен")

    composition.use_swarm_demand(monkeypatch, _demand)
    prep = _Prep(number=3, release=rel("weak"))
    prep.video = TorrFile(0, "movie.mkv", 4 * GB)
    forgotten: list[_Prep] = []

    taken = _weak_alive(PROFILE, Torrents(), (0.42, 4.0, 9.54, prep), _Tally(), forgotten.append)

    assert taken is prep
    assert not forgotten


#: Служба не ответила на ``status``: сеть, таймаут, упавший TorrServer.
SILENT = object()


class _Counter(Torrents):
    """Счётчик приёма до спроса и после: число, ``None`` - поля нет, :data:`SILENT` - молчание."""

    def __init__(self, before: object, after: object) -> None:
        super().__init__()
        self.before, self.after, self.demanded = before, after, False

    def status(self, torrent_hash: str) -> dict[str, JsonValue]:
        read = self.after if self.demanded else self.before
        if read is SILENT:
            raise ConnectionError("служба молчит")
        return {} if read is None else {"bytes_read": cast(float, read)}


@pytest.mark.parametrize(
    ("before", "after"),
    [
        pytest.param(SILENT, SILENT, id="service-silent"),
        pytest.param(None, None, id="no-bytes-read-field"),
        pytest.param(SILENT, 5_000_000_000.0, id="before-silent-after-answers"),
        pytest.param(1_000_000.0, SILENT, id="after-silent"),
        pytest.param(5_000_000.0, 1_000_000.0, id="counter-went-back"),
    ],
)
def test_an_unread_intake_counter_is_no_verdict(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    before: object,
    after: object,
) -> None:
    """Отказ сети не приговор: без счётчика рой судится по вехам, как до перемера."""
    torrents = _Counter(before, after)

    def _demand(source: str, offset: int, seconds: float) -> None:
        torrents.demanded = True

    composition.use_swarm_demand(monkeypatch, _demand)
    prep = _Prep(number=3, release=rel("weak"))
    prep.video = TorrFile(0, "movie.mkv", 4 * GB)
    tally, forgotten = _Tally(), list[_Prep]()
    tally.judged[3] = "рой короток"

    taken = _weak_alive(PROFILE, torrents, (0.05, 0.48, 9.54, prep), tally, forgotten.append)

    said = capsys.readouterr().out
    assert taken is prep
    assert not forgotten
    assert 3 not in tally.judged
    assert "под спросом" not in said
    assert "рой релиза 3 везёт 0.48 при нужных 9.54 Мбит/с - беру (0.05x)" in said


ENGLISH = Media(RUNTIME, (AudioTrack(index=0, language="eng"),), "h264", height=1080, width=1920)


def _fallback(
    monkeypatch: pytest.MonkeyPatch, media: list[Media], alive: set[str], seen: list[Bench]
) -> int:
    """Очередь из ``media``; под спросом везут только раздачи из ``alive`` (12 Мбит/с)."""
    torrents = _Stalled()

    def _demand(source: str, offset: int, seconds: float) -> None:
        if any(f"hash-magnet-{name}/" in source for name in alive):
            torrents.intake += 1_500_000.0 * seconds

    composition.use_swarm_demand(monkeypatch, _demand)
    pool = [rel(name) for name in ("one", "two")[: len(media)]]
    bench = Bench(torrents, prober=probes(pool, *media), profile=PROFILE, lends=True)
    seen.append(bench)
    return bench.resolve(plan(pool), Args(query=["кино"]), Said()).number


def test_a_dead_swarm_is_not_played_by_the_foreign_voice_fallback_either(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Запасной без русской дорожки суда роя в обходе не проходит - граница ловит его здесь."""
    seen: list[Bench] = []
    with pytest.raises(NotFoundError, match=r"русской озвучки нет ни в одной"):
        _fallback(monkeypatch, [ENGLISH], set(), seen)

    assert not seen[0].spared, "снятый мёртвый запасной показу не оставляют"
    said = capsys.readouterr().out
    assert "включаю релиз" not in said
    assert "рой релиза 1 и под спросом везёт 0.00" in said


def test_the_fallback_names_the_russian_release_lost_to_a_dead_swarm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """«Русской озвучки нет нигде» было бы неправдой: она была, но рой её не довезёт."""
    assert _fallback(monkeypatch, [MEDIA, ENGLISH], {"two"}, []) == 2

    said = capsys.readouterr().out
    assert "русская озвучка была только у раздач, чей рой кадра не довезёт (релиз 1)" in said
    assert "русской озвучки нет ни в одной" not in said


def test_a_named_dead_swarm_is_called_by_the_number_the_human_typed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--release 69`` на третьей в плане раздаче: и строка роя, и отказ говорят 69."""
    torrents = _Counter(1_000_000.0, 1_000_000.0)
    composition.use_swarm_demand(monkeypatch, lambda source, offset, seconds: None)
    prep = _Prep(number=3, release=rel("weak"))
    prep.video = TorrFile(0, "movie.mkv", 4 * GB)
    tally = _Tally(shown={3: 69}, tried=["69 - рой короток"])

    assert (
        _weak_alive(PROFILE, torrents, (0.05, 0.48, 9.54, prep), tally, list[_Prep]().append)
        is None
    )

    assert "рой релиза 69 и под спросом везёт 0.00" in capsys.readouterr().out
    assert tally.tried[0].startswith("69 - рой везёт 0.00")
