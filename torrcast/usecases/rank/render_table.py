"""Таблица релизов для меню и `cast releases`; зовут команда релизов и выбор раздачи."""

from __future__ import annotations

from torrcast.domain.rank_settings import TABLE_LIMIT
from torrcast.domain.release import Release
from torrcast.usecases.choice.warned import warned
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
    """Таблица релизов: N · качество · размер · сиды · озвучка · студия · кодек. Битрейт
    для пометки прикидывается по размеру и типовой длительности, пока настоящая не
    прочитана ffprobe; ниже ``limit`` — раздачи без сидов, выбирать там нечего.

    Колонка «Озвучка» называет ВИД перевода (дубляж, многоголосый), а «Студия» - того,
    кто его сделал, и без неё выбрать раздачу руками нельзя: у сериала все строки
    подписаны одинаково («Дубляж, Многоголосый»), и какая из них та самая, которой
    смотрели сезон, по таблице не видно. Студии перечисляются в том же порядке, в каком
    их называет имя раздачи (:attr:`~torrcast.domain.release.Release.studios`), - обычно
    это и есть порядок дорожек в файле. Пусто - ни одной знакомой студии имя не назвало;
    таблица заведомо неполная, и молчание тут значит «не узнали», а не «их нет».
    """
    shown = releases[:limit]
    rows = [
        (
            str(number),
            r.quality or "?",
            _gb(r.size),
            str(r.seeders),
            _cut(", ".join(r.voices) or "-", 34),
            _cut(", ".join(studio.name for studio in r.studios) or "-", 34),
            ((r.codec or "?") + " " + warned(r, runtime, warn_mbit, recode_at, hard_mbit)).strip(),
        )
        for number, r in enumerate(shown, start=1)
    ]
    head = ("N", "Качество", "Размер", "Сиды", "Озвучка", "Студия", "Кодек")
    width = [max(len(c[i]) for c in (head, *rows)) for i in range(len(head))]

    def line(cells: tuple[str, ...]) -> str:
        return "  " + "  ".join(_pad(c, w) for c, w in zip(cells, width, strict=True))

    out = ["Релизы:", line(head), *(line(row).rstrip() for row in rows)]
    if len(releases) > len(shown):
        out.append(f"  ... и ещё {len(releases) - len(shown)} с меньшим числом сидов")
    return "\n".join(out)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - len(text))
