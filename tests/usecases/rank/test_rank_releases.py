"""Порядок меню: лестница ступеней отбора, от годности до сидов."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.episode import Episode
from torrcast.usecases.rank.rank_releases import rank_releases


def _order(releases: list[object], **kwargs: object) -> list[str]:
    ranked = rank_releases(releases, RUNTIME, 20.0, **kwargs)  # type: ignore[arg-type]
    return [r.raw_name for r in ranked]


def test_the_default_is_the_most_seeded_candidate() -> None:
    top = rel(name="top", seeders=900)
    hevc = rel(name="hevc", codec="HEVC", seeders=800)
    good = rel(name="good", seeders=200)
    meh = rel(name="meh", seeders=10)
    assert _order([hevc, meh, top, good]) == ["top", "good", "meh", "hevc"]


def test_zero_seeders_sink_below_everyone_alive() -> None:
    """Ступень стоит выше качества: ноль сидов - это отсутствие показа."""
    assert _order([rel(name="мёртвый", seeders=0), rel(name="живой", seeders=3)]) == [
        "живой",
        "мёртвый",
    ]


def test_a_disc_image_is_always_at_the_bottom() -> None:
    disc = rel(name="Кино BDMV", seeders=900)
    assert _order([disc, rel(name="обычный", seeders=10)]) == ["обычный", "Кино BDMV"]


def test_a_release_without_the_episode_goes_under_everything() -> None:
    """Такой релиз не «хуже качеством», а бесполезен: играть в нём нечего."""
    piece = rel(name="огрызок", kind="tv", seasons=(1,), episodes=(1, 2), seeders=900)
    whole = rel(name="полный", kind="tv", seasons=(1,), seeders=1)
    assert _order([piece, whole], want=Episode(1, 5)) == ["полный", "огрызок"]


def test_a_live_1080p_beats_a_more_seeded_720p() -> None:
    full = rel(name="полный", quality="1080p", seeders=59)
    hd = rel(name="обычный", quality="720p", seeders=146)
    assert _order([hd, full]) == ["полный", "обычный"]


def test_a_seeded_oldie_yields_to_a_decent_release() -> None:
    """«Моана 2»: 1.46-гигабайтный .avi с 221 сидом стоял выше WEB-DL-AVC со 140."""
    old = rel(name="старьё", quality=None, source="WEB-DL", size_gb=1.46, seeders=221)
    fresh = rel(name="годный", quality=None, source="WEB-DL", size_gb=8, seeders=140)
    assert _order([old, fresh]) == ["годный", "старьё"]


def test_a_whole_recode_is_taken_last_of_the_good_ones() -> None:
    """Ремукс на 36 Мбит/с обязан уступать честному релизу на 8, даже с большим роем."""
    remux = rel(name="ремукс", size_gb=28, seeders=900)
    plain = rel(name="обычный", size_gb=8, seeders=10)
    assert _order([remux, plain], hard_mbit=20.0) == ["обычный", "ремукс"]


def test_a_single_film_outranks_a_more_seeded_collection() -> None:
    """Дилогия остаётся запасной: у одиночной раздачи не надо угадывать файл части."""
    both = rel(name="Брат. Дилогия (1997-2000) WEB-DL 1080p", collection=True, seeders=7)
    single = rel(name="Брат (1997) WEB-DL 1080p", seeders=5)

    assert _order([both, single]) == ["Брат (1997) WEB-DL 1080p", both.raw_name]
