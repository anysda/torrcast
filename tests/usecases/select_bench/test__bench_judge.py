"""``--judge``: названную раздачу отбор судит так же, как свою."""

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.select_bench.bench import Bench


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские приговоры отбора."""


#: 4K-ремукс: сплошной перекод такого на четырёх ядрах идёт вровень с показом.
REMUX = Media(RUNTIME, (), "hevc", height=2160, width=3840, video_bps=48e6)
FHD = Media(RUNTIME, (), "hevc", height=1080, width=1920, video_bps=3e6)


def _resolve(media: Media, args: Args) -> int:
    pool = [rel("one")]
    bench = Bench(Torrents(), prober=probes(pool, media))
    return bench.resolve(plan(pool, warn_mbit=40.0, hard_mbit=25.0), args, Said()).number


def test_a_named_release_is_not_judged_without_the_flag() -> None:
    """Человек назвал раздачу сам - отбор её не судит, как и раньше."""
    assert _resolve(REMUX, Args(query=["кино"], release=1)) == 1


def test_judge_gives_a_named_release_the_selection_verdict() -> None:
    """Приговор вместо показа - тем же словом, каким отбор отказал бы своей раздаче."""
    with pytest.raises(NotFoundError, match="перекод такого кадра этой машине не по силам"):
        _resolve(REMUX, Args(query=["кино"], release=1, judge=True))


def test_judge_lets_a_named_release_that_fits_play() -> None:
    """Приговор не придирка: годную названную раздачу ``--judge`` играет."""
    assert _resolve(FHD, Args(query=["кино"], release=1, judge=True)) == 1
