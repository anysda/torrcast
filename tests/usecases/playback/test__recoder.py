"""Зеркало подъёма кодировщика тяжёлых кусков: когда он нужен и когда честно отказывает."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fakes import composition
from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.playback._recoder import _recoder


@pytest.fixture(autouse=True)
def _tract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карта опорных кадров - готовая: ffprobe за ней тут не стоит.

    Профиль тяжести и оба кодировщика остаются теми, что положил корень: зеркало меряет
    решение подъёма на настоящих классах адаптера, а не на пересказе их подделкой.
    """
    composition.use_film_keys(monkeypatch, lambda source: film_keys())


def test_recoding_switched_off_needs_no_recoder(tmp_path: Path) -> None:
    """Перекод выключен настройкой - кодировщика нет, и спрашивать карту незачем."""
    assert _recoder("http://ts", 0, grid(), tmp_path, Config(recode=False)) is None


def test_a_uniform_grid_still_gets_something_to_shrink_the_heavy_piece_with(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-693. Ровная сетка больше не отменяет кодировщик: иначе кусок ПРОПАДАЕТ.

    Живой замер на приставке: врущий индекс отвергнут, сетка ровная, кодировщика нет, и
    выкладке нечем ужать тяжёлый кусок - пропущено 39 упакованных кусков из 39, ни кадра
    зрителю, три прогона из трёх. Резать ровную сетку копией нельзя, а перекодом можно:
    опорный кадр на границе ставит сам кодировщик.
    """
    made = _recoder(
        "http://ts",
        0,
        Grid.uniform(300.0),
        tmp_path,
        Config(recode=True),
        video_mbit=16.0,
        profile=CAUTIOUS,
    )

    assert made is not None, "на ровной сетке тяжёлый кусок иначе не ужать ничем"


def test_a_lying_index_leaves_every_heavy_piece_to_the_recoder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 TC-693, живой случай целиком: индекс врун - ни карты, ни сетки по кадрам.

    Тогда про каждый кусок известно одно - средний вес фильма, и по нему копия каждого
    куска не влезает в потолок приёмника. Значит взять кодировщик обязан КАЖДЫЙ: пропуск
    любого из них - это то самое место без картинки, которого зритель не поймёт.
    """

    asked: list[str] = []

    def lying(source: str) -> object:
        asked.append(source)
        raise InfraError("индекс Cues врёт")

    composition.use_film_keys(monkeypatch, lying)
    made = _recoder(
        "http://ts",
        0,
        Grid.uniform(300.0),
        tmp_path,
        Config(recode=True),
        video_mbit=16.0,
        profile=CAUTIOUS,
    )

    assert made is not None
    assert made.targets == tuple(range(30)), "кусок мимо кодировщика - это пропажа места"
    assert not asked, "за картой пошли второй раз: ровной сетка и вышла из-за её отсутствия"


def test_a_keymap_that_never_came_leaves_a_flat_profile_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карты нет - профиль ровный по паспорту, и какой взят, сказано числом.

    Отказ тут стоил бы показа целиком: без кодировщика тяжёлый кусок не ужимается, а
    пропадает. Ровный профиль тяжёлое место в лицо не знает и потому судит по среднему.
    """

    def dead(_source: str) -> object:
        raise InfraError("рой молчит")

    composition.use_film_keys(monkeypatch, dead)

    made = _recoder("http://ts", 0, grid(), tmp_path, Config(recode=True), video_mbit=16.0)

    said = capsys.readouterr().out
    assert made is not None
    assert "карта опорных кадров не снята" in said
    assert "профиль тяжести ровный" in said


def test_a_silent_passport_still_raises_the_recoder_for_the_last_resort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ни карты, ни веса дорожки - тяжёлых кусков не назвать, но ужимать по факту есть чем.

    Кодировщик тут не работает впрок (называть ему нечего), зато он существует - а значит
    у выкладки есть чем ужать кусок на месте, когда его вес окажется известен точно
    (:func:`torrcast.usecases.feed_pack.feed_shrink._shrink`).
    """

    def dead(_source: str) -> object:
        raise InfraError("рой молчит")

    composition.use_film_keys(monkeypatch, dead)

    made = _recoder("http://ts", 0, Grid.uniform(300.0), tmp_path, Config(recode=True))

    assert made is not None
    assert not made.targets
    assert "профиля тяжести нет" in capsys.readouterr().out


def test_a_healthy_map_raises_the_recoder_and_says_its_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карта есть - кодировщик поднимается, а профиль тяжести называется числом."""
    made = _recoder(
        "http://ts", 0, grid(), tmp_path, Config(recode=True), video_mbit=8.0, profile=CAUTIOUS
    )

    assert made is not None
    assert made.encode.mbit > 0.0
    assert "профиль тяжести:" in capsys.readouterr().out


def test_the_flat_profile_names_a_measurement_and_an_estimate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Одинаковое число не скрывает, паспортное оно или оценочное."""
    _recoder("http://ts", 0, grid(), tmp_path, Config(recode=True), video_mbit=8.0)
    measured = capsys.readouterr().out
    _recoder(
        "http://ts",
        0,
        grid(),
        tmp_path,
        Config(recode=True),
        video_mbit=8.0,
        video_mbit_estimated=True,
    )
    estimated = capsys.readouterr().out

    assert "по замеру" in measured
    assert "по оценке" in estimated


def test_a_map_without_offsets_falls_back_to_the_flat_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карта прошлой версии смещений не несёт - берётся ровный профиль, и это сказано."""
    composition.use_film_keys(monkeypatch, lambda source: film_keys()._replace(offset=[]))

    made = _recoder("http://ts", 0, grid(), tmp_path, Config(recode=True), video_mbit=16.0)

    said = capsys.readouterr().out
    assert made is not None
    assert "карта без смещений" in said
    assert "профиль тяжести ровный" in said
