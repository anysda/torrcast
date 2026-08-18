"""Картина, у которой русская дорожка обещана только в неиграбельных раздачах."""

from __future__ import annotations

from tests.usecases.reinforce.stand import franchise, row
from torrcast.cli.args import Args
from torrcast.domain.config import Config
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.reinforce.voiceless_pool import voiceless_pool

#: Единственный кандидат «тачек» - англоязычный BluRay: играть его по-русски нечем.
_ENGLISH = row("Тачки / Cars (2006) BluRay 1080p", "e", size_gb=8.0, seeders=66)
#: Дубляж обещан 38-гигабайтным 4К-ремуксом, который потолок битрейта не пускает по делу.
_HEAVY_DUB = row("Тачки / Cars (2006) UHD BDRemux 2160p | D", "d", size_gb=38.0, seeders=20)


def _asked(rows: list[RawResult], query: str = "тачки") -> Picture | None:
    return voiceless_pool(franchise(query, rows), Args(query=[query]), Config())


def test_a_dub_lying_where_selection_never_goes_is_a_reason_to_ask_again() -> None:
    """🔴 Русская дорожка - часть «включилось», а не предпочтение (TC-178)."""
    picture = _asked([_ENGLISH, _HEAVY_DUB])

    assert picture is not None
    assert (picture.title, picture.original, picture.year) == ("Тачки", "Cars", 2006)


def test_a_playable_dub_leaves_the_circle_unpaid() -> None:
    """Пока живая годная раздача русский обещает, переспрашивать не за чем."""
    playable = row("Тачки / Cars (2006) BDRip 1080p | D", "f", size_gb=5.0, seeders=61)

    assert _asked([_ENGLISH, playable]) is None


def test_a_pool_that_merely_keeps_silent_about_sound_is_not_a_reason() -> None:
    """Молчание имён вполне может скрывать дубляж - его рассудит ffprobe, а не круг."""
    assert _asked([_ENGLISH]) is None


def test_a_series_is_left_to_its_own_seasonal_circle() -> None:
    """«Оригинал + год» - приём каталога полнометражного кино: сезон-пак им не вытащить.

    ⚠️ Выдача тут подобрана так, чтобы сериал отсекала ИМЕННО проверка на ``tv``.
    Сезон-пак без года круг отбросил бы как картину без года, а сезон-пак с играбельным
    дубляжом - как пул, которому и переспрашивать не за чем: в обоих случаях снятая
    проверка оставляет зеркало зелёным, ничего не померив. Поэтому год в именах есть,
    а дубляж лежит в образе диска, куда отбор не ходит, - ровно как у «Тачек» выше.
    """
    rows = [
        row("Ангел / Angel (1999) S01 BDRip 1080p", "g", size_gb=8.0, seeders=66),
        row("Ангел / Angel (1999) S01 BDMV 1080p | D", "h", size_gb=90.0, seeders=20),
    ]

    assert _asked(rows, "ангел") is None


def test_without_an_original_there_is_no_exact_line_to_ask() -> None:
    """Точной строки не собрать - тогда и круга нет: спрашивать нечем."""
    rows = [
        row("Крестьяне (2023) BluRay 1080p", "i", size_gb=8.0, seeders=66),
        row("Крестьяне (2023) UHD BDRemux 2160p | D", "j", size_gb=38.0, seeders=20),
    ]

    assert _asked(rows, "крестьяне") is None
