"""Слабый рой отсеивается внутри отбора, пока зритель ещё не видел картинки."""

from dataclasses import replace

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.media import Media
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.json_value import JsonValue
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench_supply import _bench_supply
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русская строка снабжения уже прогретого кандидата."""


class _DifferentSupply(Torrents):
    def status(self, torrent_hash: str) -> dict[str, JsonValue]:
        step = 0 if "slow" in torrent_hash else 4_000_000
        self.read[torrent_hash] = self.read.get(torrent_hash, 0) + step
        return {"bytes_read": self.read[torrent_hash]}


def test_slow_front_is_rejected_and_fat_supply_plays(capsys: object) -> None:
    slow, fat = rel("slow"), rel("fat")
    media = Media(RUNTIME, (), "h264", height=1080, width=1920)
    profile = replace(CAUTIOUS, supply_settle_seconds=0.0, supply_ratio=1.25)
    bench = Bench(_DifferentSupply(), prober=probes([slow, fat], media, media), profile=profile)

    chosen = bench.resolve(plan([slow, fat]), Args(query=["кино"]), Said())

    assert chosen.number == 2, "слабая голова доехала до показа вместо жирного запасного"
    said = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "релиз 1 не годится (рой везёт" in said


def test_best_is_kept_when_every_swarm_is_short(capsys: object) -> None:
    one, two = rel("slow-one"), rel("slow-two")
    media = Media(RUNTIME, (), "h264", height=1080, width=1920)
    profile = replace(CAUTIOUS, supply_settle_seconds=0.0, supply_ratio=10.0)
    bench = Bench(_DifferentSupply(), prober=probes([one, two], media, media), profile=profile)

    chosen = bench.resolve(plan([one, two]), Args(query=["кино"]), Said())

    assert chosen.number == 1
    said = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "ни один проверенный рой не тянет - беру лучший" in said


def test_the_stick_does_not_condemn_a_swarm_before_its_measured_settle_time() -> None:
    release = rel("good-after-settle")
    prep = _Prep(number=1, release=release)
    prep.video = TorrFile(0, "movie.mkv", 8 * 1024**3)
    prep.media = Media(RUNTIME, (), "h264")
    prep.supply = [(1.0, 0.0), (2.0, 0.0)]

    assert _bench_supply(CAUTIOUS, prep)[0] == 0.0, "нулевое окно измерено, а не потеряно"
    assert _bench_supply(ANDROID_TV, prep)[0] < 0.0, (
        "до измеренных 10 с мера ещё молчит: неизвестное снабжение обязано пройти отбор"
    )
