"""Слабый рой отсеивается внутри отбора, пока зритель ещё не видел картинки."""

from dataclasses import replace

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.media import Media
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.json_value import JsonValue
from torrcast.usecases.select_bench.bench import Bench


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
