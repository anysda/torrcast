"""Зеркало подъёма кодировщика тяжёлых кусков: когда он нужен и когда честно отказывает."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.usecases.playback.world import film_keys, grid
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.playback.en import en as _playback_en
from torrcast.domain.catalogs.playback.ru import ru as _playback_ru
from torrcast.domain.catalogs.tongue import RU, tongue
from torrcast.domain.config import Config
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.playback._recoder import _recoder


def _prefix(key: str) -> str:
    """Постоянная часть надписи каталога - текст до первой подстановки."""
    catalog = _playback_ru() if tongue() == RU else _playback_en()
    return catalog[key].split("{", 1)[0].strip()


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


def test_a_lying_index_leaves_every_heavy_piece_to_the_recoder(tmp_path: Path) -> None:
    """🔴 TC-693, живой случай целиком: индекс врун - ни карты, ни сетки по кадрам.

    Тогда про каждый кусок известно одно - средний вес фильма, и по нему копия каждого
    куска не влезает в потолок приёмника. Значит взять кодировщик обязан КАЖДЫЙ: пропуск
    любого из них - это то самое место без картинки, которого зритель не поймёт.

    ⚠️ Ровная сетка тут ПУСТАЯ - карты у неё нет вовсе (:attr:`Grid.keys`), и это уже не
    единственный сорт ровной сетки: та, что несёт отвергнутую карту, судится по ней, а
    не по среднему.
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

    assert made is not None
    assert made.targets == tuple(range(30)), "кусок мимо кодировщика - это пропажа места"


def test_a_keymap_that_never_came_leaves_a_flat_profile_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карты нет - профиль ровный по паспорту, и какой взят, сказано числом.

    Отказ тут стоил бы показа целиком: без кодировщика тяжёлый кусок не ужимается, а
    пропадает. Ровный профиль тяжёлое место в лицо не знает и потому судит по среднему.

    ⚠️ Беду снятия карты называет вслух сама постройка сетки
    (:func:`~torrcast.adapters.stream_pack.grid_for.grid_for`), и второй раз о ней не
    докладывают: кодировщик карту у полки больше не спрашивает - он берёт ту, которую
    сетка принесла.
    """
    made = _recoder(
        "http://ts", 0, Grid.uniform(300.0), tmp_path, Config(recode=True), video_mbit=16.0
    )

    assert made is not None
    assert _prefix("recoder.flat_profile") in capsys.readouterr().out


def test_a_silent_passport_still_raises_the_recoder_for_the_last_resort(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ни карты, ни веса дорожки - тяжёлых кусков не назвать, но ужимать по факту есть чем.

    Кодировщик тут не работает впрок (называть ему нечего), зато он существует - а значит
    у выкладки есть чем ужать кусок на месте, когда его вес окажется известен точно
    (:func:`torrcast.usecases.feed_pack.feed_shrink._shrink`).
    """

    made = _recoder("http://ts", 0, Grid.uniform(300.0), tmp_path, Config(recode=True))

    assert made is not None
    assert not made.targets
    assert _prefix("recoder.no_profile") in capsys.readouterr().out


def test_a_healthy_map_raises_the_recoder_and_says_its_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карта есть - кодировщик поднимается, а профиль тяжести называется числом."""
    made = _recoder(
        "http://ts", 0, grid(), tmp_path, Config(recode=True), video_mbit=8.0, profile=CAUTIOUS
    )

    assert made is not None
    assert made.encode.mbit > 0.0
    assert _prefix("recoder.profile_container") in capsys.readouterr().out


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

    assert phrase("recoder.basis_measurement") in measured
    assert phrase("recoder.basis_estimate") in estimated


def test_a_map_without_offsets_falls_back_to_the_flat_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Карта прошлой версии смещений не несёт - берётся ровный профиль, и это сказано."""
    blind = replace(grid(), keys=film_keys()._replace(offset=[]))

    made = _recoder("http://ts", 0, blind, tmp_path, Config(recode=True), video_mbit=16.0)

    said = capsys.readouterr().out
    assert made is not None
    assert _prefix("recoder.map_no_offsets") in said
    assert _prefix("recoder.flat_profile") in said


def test_a_uniform_grid_that_carries_a_map_knows_its_heavy_places_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-839. Ровная сетка со снятой картой получает профиль ПО КАРТЕ, а не ровный.

    Отказ от врущей карты переводит показ на ровную сетку, и это правильно: кадров на её
    границах нет, резать по ним нечем. Но байты той же карты честные - это настоящие
    позиции кластеров, - и вес каждого куска по ним считается.

    Мера тут - в самих номерах слотов, и подделать её ровным профилем нельзя: ровный
    профиль по построению объявляет тяжёлыми либо ВСЕ куски, либо НИ ОДНОГО
    (:meth:`torrcast.adapters.recode.weights.Weights.flat`), а названная тут ПОЛОВИНА
    возможна только по карте. Паспорт при этом молчит (``video_mbit`` ноль) - то есть
    ровно то боевое условие, в котором у «Матрицы» стоит ``vbps: -1.0``.

    Цена, которую это снимает, замерена живьём парной мерой 3 на 3 на приставке: без
    профиля все 41 кусок уходили через ужатие на месте, указатель приёмника шёл 0.40-0.44x
    и откатывался назад на 433-953 с.
    """
    #: Первая половина фильма лёгкая (1 Мбит/с), вторая тяжёлая (20 Мбит/с).
    at = [round(n * 2.0, 3) for n in range(151)]
    offset: list[int] = [0]
    for step in at[1:]:
        offset.append(offset[-1] + (250_000 if step <= 150.0 else 5_000_000))
    keys = FilmKeys(at=at, duration=300.0, offset=offset)

    made = _recoder(
        "http://ts",
        0,
        replace(Grid.uniform(300.0), keys=keys),
        tmp_path,
        Config(recode=True),
        profile=CAUTIOUS,
    )

    said = capsys.readouterr().out
    assert made is not None
    assert made.targets == tuple(range(15, 30)), "тяжёлое место названо не по карте"
    assert _prefix("recoder.profile_container") in said
    assert _prefix("recoder.map_not_grid") in said


def test_a_uniform_grid_without_a_map_stays_on_the_flat_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Отрицательная проба к соседней: та же ровная сетка БЕЗ карты - и тяжёлых нет вовсе.

    Пара нужна затем, что «назвал половину кусков» доказывает карту только рядом с «без
    карты не назвал ни одного»: иначе тот же список мог бы прийти от любого правила.
    """
    made = _recoder("http://ts", 0, Grid.uniform(300.0), tmp_path, Config(recode=True))

    assert made is not None
    assert not made.targets
    assert _prefix("recoder.no_profile") in capsys.readouterr().out
