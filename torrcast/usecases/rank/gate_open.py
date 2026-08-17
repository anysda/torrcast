"""Пора ли открыть ворота отбора; зовут план картины и добор кандидатов."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.rank_settings import GATE_LIVENESS
from torrcast.domain.release import Release
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.misses_episode import misses_episode


def gate_open(
    releases: list[Release],
    runtime: float,
    warn_mbit: float,
    want: Episode | None = None,
    hard_mbit: float = 0.0,
    copy_hevc: bool = False,
) -> bool:
    """Пора ли открыть ворота отбора: живого именного кандидата у картины нет.

    ``copy_hevc`` приходит из профиля и делает HEVC обычным именным кандидатом только
    для ресивера, который объявил его играющим копией через наш HLS.

    Ворота (:attr:`Release.prime`) защищают от мусора и делают это по делу — пока в
    выдаче есть из чего выбирать. У аниме выбирать нечасто есть из чего: имена раздач
    там сплошь без разрешения, кодека и HD-источника, и ворота оставляют картину вообще
    без живых кандидатов. Живой случай, ради которого написано: «Наруто» (2002) — полный
    сериал «[E220 of 220] [RUS(ext), ENG, JAP+Sub] … DVDRip», 157 ГБ, 91 сид, в
    кандидаты не проходит; проходят «[1-5 из 220]» на 3 сида и «[S01E01-08 of 220]» на
    один. Очередь из двух умирающих огрызков — это не защита от мусора, это отсутствие
    показа.

    «Живой» здесь — доля от лидера пула (:data:`GATE_LIVENESS`), как и у
    :func:`is_full_hd`: абсолютное число в пулах разной населённости значит разное.
    Раздачи, у которых нужной серии нет по их же имени, в счёт не идут — они и в
    очередь не попадают.

    Ворота остаются закрытыми и тогда, когда живых нет вовсе (лидер пула на нуле
    сидов): открывать их незачем, показывать всё равно нечего.
    """
    alive = max((r.seeders for r in releases), default=0)
    if alive <= 0:
        return False
    return not any(
        r.seeders >= alive * GATE_LIVENESS
        and is_candidate(r, runtime, warn_mbit, hard_mbit=hard_mbit, copy_hevc=copy_hevc)
        and not misses_episode(r, want)
        for r in releases
    )
