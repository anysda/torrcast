"""Вид, взятый у соседки по выдаче: что правило берёт и чего НЕ берёт."""

from __future__ import annotations

from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.sibling_kind import sibling_kind

#: Немая раздача из карточки TC-854: ни сезона, ни номера серии в имени.
MUTE = "[Trix] Cyberpunk: Edgerunners (2022) [Optional Dual Audio] [Multi Subs] (720p AV1)"
#: Соседка по той же выдаче, назвавшая сезон ЯВНО.
NAMED = "Киберпанк: Бегущие по краю / Cyberpunk: Edgerunners [S01] (2022) BDRip"
#: Соседка, чья сериальность УГАДАНА голым диапазоном: права голоса не имеет.
GUESSED = "Форсаж 1-6. Коллекция / The Fast And The Furious 1-6. Collection (2001-2013) BDRip"
#: Часть той же франшизы, которую угадавшая соседка не вправе перекрасить.
FRANCHISE = "The Fast and The Furious Collection [2001-2023] BluRay HEVC x265 10Bit DTS AC3"


def kinds(names: list[str]) -> dict[str, str]:
    """Вид каждой раздачи после того, как соседки высказались."""
    done = sibling_kind([parse_release_name(name) for name in names])
    return {release.raw_name: release.kind for release in done}


def test_a_named_season_lends_its_kind_to_the_mute_release() -> None:
    """Немая раздача берёт вид у соседки с явным сезоном."""
    assert parse_release_name(MUTE).kind == "movie"  # ДО: вид поставлен молчанием
    assert kinds([MUTE, NAMED])[MUTE] == "tv"


def test_a_release_alone_in_the_results_keeps_its_kind() -> None:
    """Занять вид не у кого - вид остаётся прежним."""
    assert kinds([MUTE])[MUTE] == "movie"


def test_a_guessed_season_lends_nothing() -> None:
    """🔴 Соседка, чей вид угадан голым диапазоном, голоса не имеет.

    Ровно этим `Форсаж [1-4]` неотличим от `Nanatsu no Taizai OVA [1-2]`: порога между
    ними нет, и чужая догадка не имеет права разъехаться по франшизе.
    """
    assert parse_release_name(GUESSED).kind == "tv"  # сам разобран сериалом
    assert parse_release_name(GUESSED).season is None  # но сезон НЕ назван
    assert kinds([FRANCHISE, GUESSED])[FRANCHISE] == "movie"


def test_a_different_picture_is_not_touched() -> None:
    """Сезон соседки не красит картину с другим именем."""
    other = "Матрица / The Matrix (1999) BDRemux 1080p"
    assert kinds([other, NAMED])[other] == "movie"


def test_a_non_video_release_is_left_alone() -> None:
    """Вид «не кино» соседкой не поднимается: саундтрек сериала - не сериал."""
    score = (
        "(Score) [WEB] Счастливые лесные друзья / The Happy Tree Friends "
        "(Official Season 1 Soundtrack) (by Ashsha Kin) - 2023 (1999), FLAC (tracks), lossless"
    )
    show = "Счастливые лесные друзья / The Happy Tree Friends [S01] (1999) WEBRip 1080p"
    assert parse_release_name(score).kind == "other"
    assert kinds([score, show])[score] == "other"


def test_the_original_title_is_enough_to_match() -> None:
    """Совпасть довольно оригиналом: русского имени у немой раздачи нет вовсе."""
    mute = "[R-Archive] カウボーイビバップ COWBOY BEBOP [English BD remux]"
    named = "Ковбой Бибоп / Cowboy Bebop [S01] (1998) BDRip-HEVC 2160p"
    assert parse_release_name(mute).kind == "movie"
    assert kinds([mute, named])[mute] == "tv"


def test_a_dated_film_is_not_repainted_by_a_series_of_another_year() -> None:
    """🔴 Одно имя носят и фильм, и сериал - спор решает год.

    `Ghost in the Shell` 1995 года полнометражный, а сериал с тем же именем вышел позже.
    По одному совпадению имени таких подмен на корпусе набиралось 12 - больше, чем весь
    выигрыш правила.
    """
    film = "Ghost in the Shell (1995) [REMUX HDR 2160p] [MULTI HEVC DTS-HDMA x265]"
    show = "Ghost in the Shell: Stand Alone Complex / Ghost in the Shell [S01] (2002) BDRip"
    assert kinds([film, show])[film] == "movie"


def test_a_yearless_voter_does_not_contradict_a_dated_release() -> None:
    """Года нет у соседки - возражения нет: бесстрочная половина и датированная одна картина."""
    dated = "Код Гиас: Восставший Лелуш / Code Geass: Lelouch of the Rebellion (2006) BDRip"
    show = "Code Geass: Lelouch of the Rebellion S01 [1-25] BDRip 1080p x264"
    assert kinds([dated, show])[dated] == "tv"


def test_the_same_year_lets_the_sibling_speak() -> None:
    """Год совпал - соседка говорит о нашей картине."""
    assert kinds([MUTE, NAMED])[MUTE] == "tv"  # обе 2022
