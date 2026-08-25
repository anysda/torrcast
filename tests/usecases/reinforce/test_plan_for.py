"""План по одной картине: пул в порядке отбора, цель сериала и знаменатель битрейта."""

from __future__ import annotations

from tests.usecases.reinforce.stand import franchise, pictures, row
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.usecases.reinforce.plan_for import plan_for


def test_the_plan_ranks_the_pool_of_its_own_picture() -> None:
    """Самая обсиженная годная раздача встаёт верхом отбора - это и есть план."""
    picture = pictures(
        [
            row("Кино / Movie (1999) BDRip 1080p", "a", seeders=10),
            row("Кино / Movie (1999) BDRip 1080p x264", "b", seeders=900),
        ]
    )[0]

    plan = plan_for(picture, Args(query=["кино"]), Config())

    assert plan.picture is picture
    assert [release.seeders for release in plan.ranked] == [900, 10]


def test_without_a_told_runtime_the_denominator_is_the_guess() -> None:
    """Прикидка «фильм это два часа» - то, чем битрейт считается, пока справка молчит."""
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a")])[0]

    plan = plan_for(picture, Args(query=["кино"]), Config())

    assert plan.runtime == RUNTIME_GUESS["movie"]


def test_the_told_runtime_goes_into_the_plan_as_known() -> None:
    """🔴 TC-185. Настоящая длительность - это и есть знаменатель битрейта."""
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a")])[0]

    plan = plan_for(picture, Args(query=["кино"]), Config(), runtime=169 * 60.0)

    assert plan.runtime == 10140.0


def test_the_series_pool_keeps_only_the_asked_season() -> None:
    """Раздачи чужих сезонов в очередь не идут, но и не теряются из счёта отсева."""
    picture = franchise(
        "ангел",
        [row("Ангел / Angel S01 1080p", "a"), row("Ангел / Angel S05 1080p", "b")],
    )[0]

    plan = plan_for(picture, Args(query=["ангел", "s01e01"]), Config())

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

    with_recode = plan_for(picture, Args(query=["кино"]), config)
    without = plan_for(picture, Args(query=["кино"]), Config(recode=False))

    assert with_recode.warn_mbit == config.bitrate_recode_mbit
    assert with_recode.hard_mbit == config.bitrate_hard_mbit
    assert with_recode.recode_at == config.recode_at_mbit
    assert without.warn_mbit == config.bitrate_warn_mbit == without.hard_mbit
    assert without.recode_at == 0.0, "порог перекода без перекодирования - не порог"


def test_the_order_asks_the_receiver_for_its_bitrate_ceiling() -> None:
    """🔴 Потолок берётся из ПРОФИЛЯ приёмника, и разные приёмники дают разный порядок.

    Одна и та же пара раздач: ~9.5 Мбит/с на 40 сидах и ~19.1 Мбит/с на 90. Осторожный
    приёмник тяжёлую перекодирует на ходу и платит за это плёнкой, поэтому берёт лёгкую;
    приставка играет обе как есть, размениваться ей не на что, и решают сиды.
    """
    from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
    from torrcast.domain.tune import tune

    picture = pictures(
        [
            row("Кино / Movie (1999) BDRip 1080p", "a", seeders=40, size_gb=8),
            row("Кино / Movie (1999) BDRip 1080p x264", "b", seeders=90, size_gb=16),
        ]
    )[0]
    args = Args(query=["кино"])

    cautious = plan_for(picture, args, tune(Config(), CAUTIOUS), CAUTIOUS)
    stick = plan_for(picture, args, tune(Config(), ANDROID_TV), ANDROID_TV)

    assert [release.seeders for release in cautious.ranked] == [40, 90]
    assert [release.seeders for release in stick.ranked] == [90, 40]


def test_a_release_above_the_receiver_ceiling_keeps_its_place_in_the_queue() -> None:
    """🔴 Каталог сузиться не имеет права: под потолком живого может не быть вовсе."""
    from torrcast.domain.profile import CAUTIOUS
    from torrcast.domain.tune import tune

    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a", seeders=90, size_gb=16)])[0]

    plan = plan_for(picture, Args(query=["кино"]), tune(Config(), CAUTIOUS), CAUTIOUS)

    assert len(plan.ranked) == 1, "единственную раздачу потолок приёмника не выкидывает"
    assert plan.candidates(Args(query=["кино"])) == [1]


def test_the_order_asks_the_receiver_for_its_codecs_too() -> None:
    """🔴 TC-766. Потолка мало: раздачу, которую декодер не берёт, лёгкой считать нельзя.

    Живой случай «Матрицы: Воскрешение»: HDR-раздача укладывается в потолок осторожного
    приёмника (9.06 при 10.0), а едет зрителю сплошным перекодом от первой секунды до
    титров. Приёмнику, который копирует десять бит, та же пара достаётся прежним порядком.
    """
    from dataclasses import replace

    from torrcast.domain.profile import CAUTIOUS
    from torrcast.domain.tune import tune

    picture = pictures(
        [
            row("Кино / Movie (1999) WEB-DL 1080p, HDR10", "a", seeders=90, size_gb=8),
            row("Кино / Movie (1999) WEB-DL 1080p", "b", seeders=40, size_gb=8),
        ]
    )[0]
    args = Args(query=["кино"])
    ten_bit = replace(CAUTIOUS, copy_depth=10)

    cautious = plan_for(picture, args, tune(Config(), CAUTIOUS), CAUTIOUS)
    tolerant = plan_for(picture, args, tune(Config(), ten_bit), ten_bit)

    assert [release.seeders for release in cautious.ranked] == [40, 90]
    assert [release.seeders for release in tolerant.ranked] == [90, 40]
    assert len(cautious.ranked) == 2, "🔴 это предпочтение, а не отсев"
