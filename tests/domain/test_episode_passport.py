"""Зеркало паспорта серии: поля берутся у СВОЕГО файла, а не у прошлой серии."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.episode_passport import episode_passport
from torrcast.domain.media import Media


def _next_episode() -> Entry:
    """Запись уже перешла на s1e2, но несёт паспорт s1e1: тяжёлый H.264 в HDR."""
    return Entry(
        title="Футурама", magnet="magnet:?x", kind="tv", file_idx=1, season=1, episode=2,
        episodes=[[1, 1, 0, 180_000_000], [1, 2, 1, 91_000_000]],
        dur=0.0, vbps=12.0, codec="h264", depth=8, frame=1080, hdr=True,
    )  # fmt: skip


def test_the_passport_replaces_every_field_of_the_previous_episode() -> None:
    """Кодек, глубина, кадр и HDR - свои у серии, вес - по размеру её строки."""
    media = Media(
        duration=1300.0, tracks=(), video="hevc", pix_fmt="yuv420p10le", height=720, width=960
    )

    entry = episode_passport(_next_episode(), media)

    assert (entry.dur, entry.codec, entry.depth, entry.frame, entry.hdr) == (
        1300.0, "hevc", 10, media.frame, False,
    )  # fmt: skip
    assert entry.vbps == 91_000_000 * 8 / 1300.0 / 1e6
    assert entry.vbps_estimated


def test_a_passport_without_duration_keeps_the_known_one() -> None:
    """Пробник промолчал о длительности - прежняя остаётся, веса без размера нет."""
    entry = episode_passport(
        Entry(title="Фильм", magnet="magnet:?x", dur=5400.0), Media(duration=0.0, tracks=())
    )

    assert (entry.dur, entry.vbps, entry.vbps_estimated) == (5400.0, -1.0, False)
