"""Таблица релизов для меню и `cast releases`; зовут команда релизов и выбор раздачи."""

from __future__ import annotations

from torrcast.domain.rank_settings import TABLE_LIMIT
from torrcast.domain.release import Release
from torrcast.usecases.choice import warned
from torrcast.usecases.rank._cut import _cut
from torrcast.usecases.rank._gb import _gb


def render_table(
    releases: list[Release],
    runtime: float,
    warn_mbit: float,
    limit: int = TABLE_LIMIT,
    recode_at: float = 0.0,
    hard_mbit: float = 0.0,
) -> str:
    """Таблица релизов: N · качество · размер · сиды · озвучка · кодек. Битрейт для
    пометки прикидывается по размеру и типовой длительности, пока настоящая не прочитана
    ffprobe; ниже ``limit`` — раздачи без сидов, выбирать там нечего.
    """
    shown = releases[:limit]
    rows = [
        (
            str(number),
            r.quality or "?",
            _gb(r.size),
            str(r.seeders),
            _cut(", ".join(r.voices) or "-", 34),
            ((r.codec or "?") + " " + warned(r, runtime, warn_mbit, recode_at, hard_mbit)).strip(),
        )
        for number, r in enumerate(shown, start=1)
    ]
    head = ("N", "Качество", "Размер", "Сиды", "Озвучка", "Кодек")
    width = [max(len(c[i]) for c in (head, *rows)) for i in range(len(head))]

    def line(cells: tuple[str, ...]) -> str:
        return "  " + "  ".join(_pad(c, w) for c, w in zip(cells, width, strict=True))

    out = ["Релизы:", line(head), *(line(row).rstrip() for row in rows)]
    if len(releases) > len(shown):
        out.append(f"  ... и ещё {len(releases) - len(shown)} с меньшим числом сидов")
    return "\n".join(out)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - len(text))
