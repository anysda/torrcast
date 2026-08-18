"""Зеркало приговора релизу: почему он не годится и чьими это словами сказано."""

from __future__ import annotations

from tests.usecases.select_bench.world import RUNTIME, Torrents, probes, rel
from torrcast.domain.media import Media
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench import _Bench

GB = 1024**3


def _judged(
    media: Media | None,
    *,
    size_gb: float = 8.0,
    recode: bool = True,
    warn_mbit: float = 0.0,
    hard_mbit: float = 0.0,
) -> str:
    bench = _Bench(Torrents(), prober=probes([]))
    prep = _Prep(number=1, release=rel())
    prep.media = media
    prep.video = TorrFile(0, "movie.mkv", int(size_gb * GB))
    return bench._trouble(
        prep, pinned=False, recode=recode, warn_mbit=warn_mbit, hard_mbit=hard_mbit
    )


def test_a_stream_that_was_never_read_is_named_as_such() -> None:
    """Паспорта нет - и это отдельная строка, а не приговор кодеку."""
    assert _judged(None) == "поток не прочитан"


def test_a_copy_playable_codec_is_no_trouble_at_all() -> None:
    """H.264 приёмник играет копией - придираться не к чему."""
    assert _judged(Media(RUNTIME, (), "h264", height=1080, width=1920)) == ""


def test_a_codec_the_receiver_refuses_is_a_verdict_by_its_own_name() -> None:
    """av1 копией не играется, а цена сплошного перекода для него не мерена."""
    assert _judged(Media(RUNTIME, (), "av1", height=1080, width=1920)) == "av1"


def test_hevc_is_not_a_refusal_while_the_recode_is_on() -> None:
    """⚠️ HEVC больше не отказ: такой файл перекодируется целиком, и аниме играет."""
    hevc = Media(RUNTIME, (), "hevc", height=1080, width=1920)

    assert _judged(hevc) == ""
    assert _judged(hevc, recode=False) == "hevc"


def test_a_release_too_heavy_for_the_receiver_is_named_by_the_weight() -> None:
    """Число берётся из паспорта, а не из размера файла, и печатается человеку то же."""
    heavy = Media(RUNTIME, (), "h264", height=1080, width=1920, video_bps=30e6)

    assert _judged(heavy, warn_mbit=20.0) == "слишком тяжёлый для приёмника, ~30 Мбит/с"


def test_a_frame_our_machine_cannot_recode_in_time_blames_the_machine() -> None:
    """Потолок, опущенный по высоте кадра, - это скорость НАШЕЙ машины, не приёмника."""
    huge = Media(RUNTIME, (), "h264", height=2160, width=3840, video_bps=30e6)

    said = _judged(huge, warn_mbit=40.0, hard_mbit=20.0)

    assert said == "перекод такого кадра этой машине не по силам, ~30 Мбит/с"
