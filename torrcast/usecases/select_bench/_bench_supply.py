"""Фактическое снабжение уже прогретого кандидата."""

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.profile import Profile
from torrcast.domain.swarm_pick import swarm_pick
from torrcast.usecases.select._prep import _Prep


def _bench_supply(profile: Profile, prep: _Prep) -> tuple[float, float, float]:
    if prep.video is None or prep.media is None:
        return -1.0, 0.0, 0.0
    measured = swarm_pick(
        prep.supply,
        prep.video.index,
        prep.video.size,
        prep.media.duration,
        profile.supply_settle_seconds,
    )
    if measured is None:
        need = prep.video.size * 8 / prep.media.duration / 1_000_000
        return -1.0, 0.0, need
    elif measured[0] >= profile.supply_ratio:
        ratio, got, need = measured
        print(
            phrase(
                "select_bench.supply_note",
                number=prep.number,
                got=f"{got:.2f}",
                need=f"{need:.2f}",
                ratio=f"{ratio:.2f}",
            )
        )
    return measured
