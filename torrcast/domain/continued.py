"""Правило continued; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.picture import Picture
from torrcast.domain.picture_season_span import _picture_season_span
from torrcast.domain.run_span import _run_span


def _continued(
    pictures: list[Picture], chains: list[list[int]], union: Callable[[int, int], None]
) -> list[list[int]]:
    if len(chains) < 2 or any(pictures[i].kind != "tv" for chain in chains for i in chain):
        return chains
    out: list[list[int]] = [chains[0]]
    for chain in chains[1:]:
        before_ep = [span for i in out[-1] if (span := _run_span(pictures[i]))]
        after_ep = [span for i in chain if (span := _run_span(pictures[i]))]
        start_ep = min((s for s, _ in after_ep), default=0)
        before_s = [span for i in out[-1] if (span := _picture_season_span(pictures[i]))]
        after_s = [span for i in chain if (span := _picture_season_span(pictures[i]))]
        start_s = min((s for s, _ in after_s), default=0)
        if (before_ep and start_ep > 1 and (start_ep <= max((e for _, e in before_ep)) + 1)) or (
            before_s and start_s > 1 and (start_s <= max((e for _, e in before_s)) + 1)
        ):
            union(out[-1][0], chain[0])
            out[-1] = out[-1] + chain
            continue
        out.append(chain)
    return out


__all__ = ["_continued"]
