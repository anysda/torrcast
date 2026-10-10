"""``--judge``: названную раздачу отбор судит так же, как свою."""

from dataclasses import replace

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.info_hash import info_hash
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


#: Раздача, названная номером строки таблицы, которую человек видел: в плане она вторая.
NAMED = replace(rel("named"), magnet="magnet:?xt=urn:btih:" + "ab" * 20)


def test_the_verdict_names_the_release_by_the_number_the_human_typed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """«Релиз 2 не годится» на ``--release 69`` читается как приговор чужой раздаче."""
    pool = [rel("one"), NAMED]
    bench = Bench(Torrents(), prober=probes(pool, FHD, REMUX))
    args = Args(query=["кино"], release=69, release_hash=info_hash(NAMED), judge=True)

    with pytest.raises(NotFoundError, match=r"годного релиза нет \(69 - перекод такого кадра"):
        bench.resolve(plan(pool, warn_mbit=40.0, hard_mbit=25.0), args, Said())

    said = capsys.readouterr().out
    assert "релиз 69 не годится" in said
    assert "релиз 2 " not in said
