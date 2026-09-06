"""Раздачу, которую входной фильтр признал видео, разбор обязан звать видеом же.

Живой случай с .64, 06-09-2026 (TC-842): «металлика» стояла в меню двумя строками -
«Металлика: Подобный монстру (2004)» и «Metallica Some Kind Of Monster (2004)».
Вторую строку рождала одна раздача ``...BRRip.XviD.MP3-RARBG``: звуковая примета
``MP3`` срабатывала, а слова ``BRRip`` вето-список видео-примет не знал, и раздача
получала вид «не кино». С таким видом склейка её ни с кем не сшивает (сторож от
саундтреков, :func:`~torrcast.domain.glue.glue`), и картина вставала в меню дважды.
"""

from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.cluster import cluster
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.raw_result import RawResult

#: Дословные строки живой выдачи .64 по запросу «металлика» и добору по оригиналу.
RUSSIAN_HALF = "Металлика: Подобный монстру / Metallica: Some kind of Monster (2004) DVDRip"
LATIN_HALF = "Metallica Some Kind of Monster (2004) 1080p BRRip x264 -YTS"
MARKED_WITH_AUDIO = "Metallica.Some.Kind.Of.Monster.2004.BRRip.XviD.MP3-RARBG"


def test_a_release_marked_as_video_stays_video_despite_an_audio_word() -> None:
    """``BRRip`` - метка видео не слабее ``BDRip``, и тег звуковой дорожки её не отменяет."""
    assert parse_release_name(MARKED_WITH_AUDIO).kind == "movie"


def test_the_audio_tagged_half_glues_into_the_one_picture() -> None:
    """Обе языковые половины и раздача с тегом ``MP3`` - один пункт меню, один пул."""
    rows = [
        RawResult(RUSSIAN_HALF, "a" * 40),
        RawResult(LATIN_HALF, "b" * 40),
        RawResult(MARKED_WITH_AUDIO, "c" * 40),
    ]
    pictures = cluster(to_releases(rows))
    assert len(pictures) == 1
    assert {r.raw_name for r in pictures[0].releases} == {
        RUSSIAN_HALF,
        LATIN_HALF,
        MARKED_WITH_AUDIO,
    }


def test_a_soundtrack_without_a_video_mark_stays_outside() -> None:
    """Встречный сторож: без видео-приметы звуковая раздача остаётся «не кино»."""
    assert parse_release_name("Metallica - Some Kind Of Monster (2004) MP3").kind == "other"
