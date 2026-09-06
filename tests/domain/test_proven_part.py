"""Голый номер и подзаголовок - два имени одной картины: склейка и её границы."""

from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.cluster import cluster
from torrcast.domain.raw_result import RawResult


def test_number_and_subtitle_share_one_pool_beside_a_living_line() -> None:
    rows = [
        RawResult(
            "Матрица 4 / Matrix 4 - As It Should Be (2021) HDRip | Фанатская версия", "a" * 40
        ),
        RawResult("Матрица: Воскрешение / The Matrix Resurrections (2021) HDRip", "b" * 40),
        RawResult("Матрица: Воскрешение / The Matrix Resurrections (2021) BDRip 1080p", "c" * 40),
        RawResult("Матрица 2: Перезагрузка / The Matrix Reloaded (2003) BDRip", "d" * 40),
        RawResult("Матрица 3: Революция / The Matrix Revolutions (2003) BDRip", "e" * 40),
    ]
    pictures = cluster(to_releases(rows))
    assert len(pictures) == 3
    merged = next(p for p in pictures if p.year == 2021)
    assert merged.title == "Матрица: Воскрешение"
    assert merged.also == "Матрица 4"
    assert merged.part == 4
    assert {r.title for r in merged.releases} == {"Матрица 4", "Матрица: Воскрешение"}


def test_number_taken_by_another_part_stays_apart() -> None:
    rows = [
        RawResult("Пираты 2 (2007) HDRip", "a" * 40),
        RawResult("Пираты: На краю света (2007) HDRip", "b" * 40),
        RawResult("Пираты 2: Сундук мертвеца (2006) HDRip", "c" * 40),
    ]
    assert len(cluster(to_releases(rows))) == 3


def test_two_same_year_candidates_stay_apart() -> None:
    rows = [
        RawResult("Матрица 3 (2003) HDRip", "a" * 40),
        RawResult("Матрица: Перезагрузка (2003) BDRip", "b" * 40),
        RawResult("Матрица: Революция (2003) BDRip", "c" * 40),
    ]
    assert len(cluster(to_releases(rows))) == 3


def test_bare_candidate_proves_the_first_part_only() -> None:
    rows = [
        RawResult("Совершенные Мстители (2006) HDRip", "a" * 40),
        RawResult("Совершенные Мстители 2 (2006) BDRip", "b" * 40),
    ]
    assert len(cluster(to_releases(rows))) == 2


def test_part_cannot_be_older_than_a_later_part() -> None:
    rows = [
        RawResult("Форсаж 3 (2020) HDRip", "a" * 40),
        RawResult("Форсаж: Подзаголовок (2020) BDRip", "b" * 40),
        RawResult("Форсаж 4: Другой подзаголовок (2010) BDRip", "c" * 40),
    ]
    assert len(cluster(to_releases(rows))) == 3
