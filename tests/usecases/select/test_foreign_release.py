"""Зеркало :func:`foreign_release`: кого из пула очередь отбора не спрашивает."""

from __future__ import annotations

import sys

import pytest

from tests.usecases.select.world import parsed, plan
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.select.foreign_release import foreign_release
from torrcast.usecases.select.plan import Plan


def _release(
    year: int | None,
    *,
    season: int | None = None,
    episodes: tuple[int, ...] = (),
    original: str | None = None,
) -> Release:
    return Release(
        raw_name="Оно",
        title="Оно",
        original=original,
        year=year,
        quality="1080p",
        seeders=10,
        season=season,
        episodes=episodes,
    )


def test_a_film_release_of_another_year_is_foreign_to_the_film() -> None:
    it = Picture(title="Оно", year=2017)

    assert foreign_release(_release(2014), it, None)
    assert not foreign_release(_release(2017), it, None)


def test_a_season_pack_without_the_asked_episode_is_foreign_to_the_episode() -> None:
    show = Picture(title="Мажор", year=2014, kind="tv")

    assert foreign_release(_release(2026, season=5, episodes=(1, 2)), show, Episode(5, 7))
    assert not foreign_release(_release(2026, season=5, episodes=(7,)), show, Episode(5, 7))


def test_a_series_of_another_work_by_the_original_is_foreign_to_the_episode() -> None:
    naruto = Picture(title="Наруто", year=2002, kind="tv", original="Naruto")

    assert foreign_release(
        _release(2007, original="Naruto: Shippuuden", season=1), naruto, Episode(1, 1)
    )


def _count_phrases(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Подменить `phrase` везде, куда его импортировали, и копить спрошенные ключи."""
    asked: list[str] = []
    real = phrase

    def counted(key: str, **values: object) -> str:
        asked.append(key)
        return real(key, **values)

    for module in list(sys.modules.values()):
        if getattr(module, "phrase", None) is phrase:
            monkeypatch.setattr(module, "phrase", counted)
    return asked


def _series_pool() -> Plan:
    """Сериал на 60 раздач: 50 без нужной серии и 10 годных."""
    wrong = [parsed(f"Кино (1999) WEB-DL 1080p | 2 сезон, 1-10 из 10 {n}") for n in range(50)]
    right = [parsed(f"Кино (1999) WEB-DL 1080p | 1 сезон, 1-10 из 10 {n}") for n in range(10)]
    return plan(*wrong, *right, series=_Series(want=Episode(1, 9)))


def test_the_queue_builds_no_phrase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Очередь судит чужие раздачи ключом, надпись ей не нужна: старт показа её ждал."""
    built = _series_pool()
    asked = _count_phrases(monkeypatch)

    assert len(built.candidates(Args(query=["кино"]))) == 10
    assert asked == []


def test_the_phrase_counter_sees_an_explained_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отрицательная проба счётчика: объяснение отсева надпись собирает, и он это видит."""
    built = _series_pool()
    asked = _count_phrases(monkeypatch)

    assert drop_reason(built.ranked[0], built)
    assert asked == ["rank.reason_no_episode"]
