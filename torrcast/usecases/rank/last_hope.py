"""Пора ли пускать в очередь названный HEVC; зовут план картины и добор кандидатов."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.release import Release
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.misses_episode import misses_episode


def last_hope(
    releases: list[Release],
    runtime: float,
    warn_mbit: float,
    want: Episode | None = None,
    loose: bool = False,
    hard_mbit: float = 0.0,
    copy_hevc: bool = False,
) -> bool:
    """Пора ли пускать в очередь названный HEVC: живого кандидата нет ВООБЩЕ.

    Ступень за :func:`gate_open`, и порог у неё жёстче нарочно. Открытые ворота ещё
    ничего не гарантируют: они пускают молчаливые имена, а те могут все до одного лежать
    с нулём сидов. Ровно это и есть «Гинтама»: 162 раздачи в каталоге, первая серия — в
    двух, и та, что проходит ворота (``DVDRip-AVC``, 99 ГБ), раздаётся нулём пиров.
    Кандидат формально есть, показа нет.

    Поэтому здесь спрашивается не «есть ли кандидат», а «есть ли кандидат, которым
    МОЖНО СЫГРАТЬ»: годен по :func:`is_candidate`, несёт нужную серию и жив. Живость —
    строгий ноль, а не доля от лидера (:func:`is_dead`): доля это размен качества на
    рой, а тут разменивать нечего — либо рой есть, либо показа нет.

    ``loose`` — те же ворота, что у самого плана: молчаливое имя, если оно живое, —
    полноценный кандидат, и последнюю надежду оно закрывает наравне с именным.

    HEVC в выдаче может и не быть вовсе — тогда открытые ворота не меняют ничего:
    признак :func:`hevc_hope` не сработает ни на одной раздаче.

    ⚠️ Про приёмник тут не спрашивается: «тяжёлый ли для него HEVC» — вопрос профиля, и
    задаёт его :func:`_plan_for` перед этой ступенью, одним и тем же
    :func:`torrcast.stream.recodes_whole` на весь код.
    """
    return not any(
        release.seeders > 0
        and is_candidate(release, runtime, warn_mbit, loose, hard_mbit, copy_hevc=copy_hevc)
        and not misses_episode(release, want)
        for release in releases
    )
