"""План по одной картине: пул в порядке отбора, цель сериала и знаменатель битрейта."""

from __future__ import annotations

from tests.usecases.reinforce.stand import franchise, pictures, row
from torrcast.cli.args import Args
from torrcast.domain.config import Config
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.usecases.reinforce._plan_for import _plan_for


def test_the_plan_ranks_the_pool_of_its_own_picture() -> None:
    """Самая обсиженная годная раздача встаёт верхом отбора - это и есть план."""
    picture = pictures(
        [
            row("Кино / Movie (1999) BDRip 1080p", "a", seeders=10),
            row("Кино / Movie (1999) BDRip 1080p x264", "b", seeders=900),
        ]
    )[0]

    plan = _plan_for(picture, Args(query=["кино"]), Config())

    assert plan.picture is picture
    assert [release.seeders for release in plan.ranked] == [900, 10]


def test_without_a_told_runtime_the_denominator_is_the_guess() -> None:
    """Прикидка «фильм это два часа» - то, чем битрейт считается, пока справка молчит."""
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a")])[0]

    plan = _plan_for(picture, Args(query=["кино"]), Config())

    assert plan.runtime == RUNTIME_GUESS["movie"]
    assert not plan.runtime_known, "прикидка не имеет права выдавать себя за знание"


def test_the_told_runtime_goes_into_the_plan_as_known() -> None:
    """🔴 TC-185. Настоящая длительность - это и есть знаменатель битрейта."""
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a")])[0]

    plan = _plan_for(picture, Args(query=["кино"]), Config(), runtime=169 * 60.0)

    assert plan.runtime == 10140.0
    assert plan.runtime_known


def test_the_series_pool_keeps_only_the_asked_season() -> None:
    """Раздачи чужих сезонов в очередь не идут, но и не теряются из счёта отсева."""
    picture = franchise(
        "ангел",
        [row("Ангел / Angel S01 1080p", "a"), row("Ангел / Angel S05 1080p", "b")],
    )[0]

    plan = _plan_for(picture, Args(query=["ангел", "s01e01"]), Config())

    assert len(picture.releases) == 2
    assert [release.season for release in plan.ranked] == [1]
    assert plan.off_season == 1


def test_the_ceiling_of_the_plan_is_the_one_recoding_allows() -> None:
    """Потолок отбора - уже не потолок декодера: тяжёлые куски перекодируются.

    Перекодирование выключено - потолком снова становится прежняя отбраковка, и порога
    перекода у плана нет вовсе. Числа берутся у настроек, а не переписываются рядом.
    """
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a")])[0]
    config = Config()

    with_recode = _plan_for(picture, Args(query=["кино"]), config)
    without = _plan_for(picture, Args(query=["кино"]), Config(recode=False))

    assert with_recode.warn_mbit == config.bitrate_recode_mbit
    assert with_recode.hard_mbit == config.bitrate_hard_mbit
    assert with_recode.recode_at == config.recode_at_mbit
    assert without.warn_mbit == config.bitrate_warn_mbit == without.hard_mbit
    assert without.recode_at == 0.0, "порог перекода без перекодирования - не порог"
