"""Живые имена с .64, 06-09-2026: одна строка меню и граница склейки."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.cluster import cluster
from torrcast.domain.raw_result import RawResult

PAIRS = json.loads((Path(__file__).parents[1] / "fixtures/katalog/subtitles.json").read_text())


@pytest.mark.parametrize(("case", "first", "second"), PAIRS, ids=[row[0] for row in PAIRS])
def test_live_number_and_subtitle_share_one_pool(case: str, first: str, second: str) -> None:
    pictures = cluster(to_releases([RawResult(first, "a" * 40), RawResult(second, "b" * 40)]))
    assert len(pictures) == 1, case
    assert {r.raw_name for r in pictures[0].releases} == {first, second}


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Матрица: Перезагрузка (2003)", "Матрица: Революция (2003)"),
        ("Пираты 2: Возвращение (2007)", "Пираты 3: Возвращение (2007)"),
        (
            "Голодные игры: Сойка-пересмешница. Часть 1 (2014)",
            "Голодные игры: Сойка-пересмешница. Часть 2 (2015)",
        ),
    ],
)
def test_different_pictures_and_unproven_aliases_stay_apart(first: str, second: str) -> None:
    assert len(cluster(to_releases([RawResult(first, "a" * 40), RawResult(second, "b" * 40)]))) == 2
