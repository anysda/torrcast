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


def test_the_remembered_studio_wins_among_equals() -> None:
    """Граница сезона: раздача кончилась вместе с сезоном, а студия остаётся та же."""
    same = rel(name="Харли Квинн S02 WEB-DL 1080p, Dub (The Kitchen Russia)", seeders=40)
    other = rel(name="Харли Квинн S02 WEB-DL 1080p, MVO (Good People)", seeders=60)
    assert _order([other, same], studio="The Kitchen Russia") == [same.raw_name, other.raw_name]


def test_without_memory_the_order_is_the_old_one() -> None:
    same = rel(name="Харли Квинн S02 WEB-DL 1080p, Dub (The Kitchen Russia)", seeders=40)
    other = rel(name="Харли Квинн S02 WEB-DL 1080p, MVO (Good People)", seeders=60)
    assert _order([other, same]) == [other.raw_name, same.raw_name]


def test_the_studio_does_not_buy_a_worse_frame() -> None:
    """Ступень стоит ПОД кадром: память про звук картинку не покупает."""
    small = rel(name="Харли Квинн S02 WEB-DL 720p, Dub (The Kitchen Russia)", quality="720p")
    full = rel(name="Харли Квинн S02 WEB-DL 1080p, MVO (Good People)", quality="1080p")
    assert _order([small, full], studio="The Kitchen Russia") == [full.raw_name, small.raw_name]


def _light_and_heavy() -> tuple[object, object]:
    """Два живых 1080p одной картины: лёгкий под потолком приёмника и тяжёлый над ним."""
    light = rel(name="лёгкий", size_gb=8, seeders=40)
    heavy = rel(name="тяжёлый", size_gb=16, seeders=90)
    return light, heavy


def test_the_receiver_ceiling_lifts_the_release_it_plays_whole() -> None:
    """Раздача, которую приёмник играет как есть, обходит равного ей соседа с бо́льшим роем."""
    light, heavy = _light_and_heavy()
    assert _order([heavy, light], recode_at=10.0) == ["лёгкий", "тяжёлый"]


def test_without_the_receiver_ceiling_the_order_is_the_old_one() -> None:
    """Потолок не назван - решают сиды, ровно как решали."""
    light, heavy = _light_and_heavy()
    assert _order([heavy, light]) == ["тяжёлый", "лёгкий"]


def test_a_release_above_the_ceiling_stays_in_the_menu() -> None:
    """🔴 Потолок приёмника - предпочтение, а не отсев: под ним живого может не быть."""
    heavy = rel(name="тяжёлый", size_gb=16, seeders=90)
    assert _order([heavy], recode_at=10.0) == ["тяжёлый"]


def test_the_receiver_ceiling_does_not_buy_the_sound() -> None:
    """Релиз без русской дорожки негоден любым весом: ступень звука стоит выше."""
    mute = rel(name="Кино (1999) BDRip 1080p [JAP+Sub]", size_gb=8, seeders=40)
    dubbed = rel(name="Кино (1999) BDRip 1080p, Дубляж", size_gb=16, seeders=40)
    assert _order([mute, dubbed], recode_at=10.0) == [dubbed.raw_name, mute.raw_name]


def test_the_receiver_ceiling_does_not_buy_the_frame() -> None:
    """720p под потолком - это не выигрыш, а другая ступень чёткости."""
    small = rel(name="малый", quality="720p", size_gb=8, seeders=40)
    full = rel(name="полный", quality="1080p", size_gb=16, seeders=40)
    assert _order([small, full], recode_at=10.0) == ["полный", "малый"]


def test_a_dead_light_release_does_not_displace_a_live_heavy_one() -> None:
    """Лёгкий на двух сидах меняет перекод на подгрузы - это не размен, а откат.

    Кадр у обеих раздач один, и спор доходит до потолка приёмника нерешённым: иначе
    мёртвую сторону утопила бы ступень чёткости, а пол живости остался бы непроверенным.
    """
    light = rel(name="лёгкий", quality="720p", size_gb=8, seeders=2)
    heavy = rel(name="тяжёлый", quality="720p", size_gb=16, seeders=90)
    assert _order([heavy, light], recode_at=10.0) == ["тяжёлый", "лёгкий"]
