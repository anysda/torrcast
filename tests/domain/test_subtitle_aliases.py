"""Спорящие номера не дают безномерному имени склеить разные картины."""

from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.cluster import cluster
from torrcast.domain.raw_result import RawResult


def test_an_unnumbered_name_cannot_bridge_conflicting_parts() -> None:
    rows = [
        RawResult(f"Пираты{part}: Возвращение (2007) HDRip", str(i) * 40)
        for i, part in enumerate((" 2", " 3", ""))
    ]
    assert len(cluster(to_releases(rows))) == 3
