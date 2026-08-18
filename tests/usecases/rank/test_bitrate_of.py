"""Оценка битрейта по размеру раздачи: у сериала - на серию, у сборника - на фильм."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.bitrate_of import bitrate_of


def test_a_movie_is_measured_whole() -> None:
    assert bitrate_of(rel(size_gb=8), RUNTIME) == pytest.approx(9.54, abs=0.01)


def test_a_series_is_measured_per_episode() -> None:
    """«9.7 ГБ» на восемь серий это 3 Мбит/с, а не 30."""
    pack = rel(name="Сериал [S01E01-08]", kind="tv", episodes=tuple(range(1, 9)), size_gb=8)
    assert bitrate_of(pack, RUNTIME) == pytest.approx(9.54 / 8, abs=0.01)


def test_a_name_that_counts_no_episodes_answers_none() -> None:
    """🔴 TC-344. «Не знаю» и «мало» - разные ответы; ноль читался бы как «лёгкий»."""
    assert bitrate_of(rel(name="Локи [S01]", kind="tv"), RUNTIME) is None


def test_a_collection_is_measured_per_film() -> None:
    two = rel(name="Дилогия (1999) BDRip 1080p", collection=True, size_gb=8)
    assert bitrate_of(two, RUNTIME) == pytest.approx(9.54 / 2, abs=0.01)
    unknown = rel(name="Коллекция (1999) BDRip 1080p", collection=True, size_gb=8)
    assert bitrate_of(unknown, RUNTIME) is None, "сколько внутри фильмов, имя не сказало"


def test_the_guess_inflates_the_bitrate_of_a_long_film() -> None:
    """🔴 TC-185. Один и тот же файл: по прикидке 19.7 Мбит/с, по настоящей длине 14.0.

    «Интерстеллар» идёт 2 ч 49 мин против прикидки в два часа - знаменатель занижен в
    1.41 раза, и честный 1080p отсекался потолком, которого он не переходил.
    """
    full = rel(name="Интерстеллар / Interstellar (2014) BDRip 1080p", size_gb=16.5, seeders=90)

    assert bitrate_of(full, RUNTIME) == pytest.approx(19.7, abs=0.1)
    assert bitrate_of(full, 169 * 60.0) == pytest.approx(14.0, abs=0.1)
