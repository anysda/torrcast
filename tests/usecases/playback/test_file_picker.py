"""Зеркало выбора файла раздачи: серия сериала, крупнейший файл фильма или ``--file N``."""

from __future__ import annotations

import pytest

from torrcast.domain.args import Args
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback.file_picker import _default_file, file_picker
from torrcast.usecases.select.plan import Plan


def _files() -> list[TorrFile]:
    """Раздача, в которой текст лежит МЕЖДУ видеофайлами.

    Порядок тут и есть предмет: положи текст в хвост - и ``--file 2`` попал бы в фильм
    и со счётом по видеофайлам, и со счётом подряд, то есть разницы между ними тест бы
    не увидел вовсе.
    """
    return [
        TorrFile(index=1, name="кино/extra.mkv", size=1),
        TorrFile(index=2, name="кино/readme.txt", size=1),
        TorrFile(index=3, name="кино/film.mkv", size=100),
    ]


def _plan() -> Plan:
    release = Release(raw_name="кино", title="Кино", magnet="magnet:?xt=1")
    return Plan(
        picture=Picture(title="Кино", year=1999, releases=[release]),
        ranked=[release],
        runtime=7200.0,
        warn_mbit=16.0,
    )


def test_a_movie_takes_the_biggest_video_file() -> None:
    """У фильма серии нет - берётся то, что назовёт медиатракт, а не первый попавшийся.

    Медиатракт тут настоящий - тот, что положил корень: подделка на его месте
    доказывала бы выбор теста, а не выбор показа.
    """
    assert _default_file(_plan(), _plan().ranked[0], _files()).index == 3


def test_the_hand_named_number_counts_only_video_files() -> None:
    """``--file N`` считает ВИДЕО раздачи по порядку, а не файлы вперемешку с текстом."""
    chosen = file_picker(Args(query=["кино"], file=2))

    assert chosen(_plan(), _plan().ranked[0], _files()).name.endswith("film.mkv")
    assert file_picker(Args(query=["кино"], file=1))(
        _plan(), _plan().ranked[0], _files()
    ).name.endswith("extra.mkv")


def test_a_number_outside_the_pool_is_a_polite_refusal() -> None:
    """Номера нет - отказ называет, сколько видеофайлов в раздаче на самом деле."""
    chosen = file_picker(Args(query=["кино"], file=9))

    with pytest.raises(NotFoundError, match="видеофайлов в раздаче 2"):
        chosen(_plan(), _plan().ranked[0], _files())


def test_without_the_flag_the_default_picker_is_returned() -> None:
    """Ручку не назвали - выбор остаётся обычным, и подмены на ней не бывает."""
    assert file_picker(Args(query=["кино"])) is _default_file


def test_a_series_named_without_season_marks_plays_as_a_movie() -> None:
    """Сериал без серийных меток в имени теряет очередь серий: играет крупнейший файл.

    🔴 Воспроизведение потери по построению: имя не назвало ни сезона, ни линейки -
    разбор ставит вид «фильм», план не заводит серии вовсе
    (:func:`~torrcast.usecases.reinforce.plan_for.plan_for` строит их только виду ``tv``),
    и единственным правилом выбора остаётся «крупнейший видеофайл»
    (:func:`_default_file`). Списка серий у записи показа тоже не будет: он пишется
    только из плана сериала. Двенадцатая серия тяжелее первой - и играет она.
    """
    from tests.usecases.reinforce.stand import pictures, row
    from torrcast.domain.config import Config
    from torrcast.usecases.reinforce.plan_for import plan_for

    picture = pictures(
        [row("Врата Штейна / Steins;Gate [2011, Япония, фантастика, BDRip 1080p] MVO", "a")]
    )[0]
    plan = plan_for(picture, Args(query=["врата штейна"]), Config())
    files = [
        TorrFile(index=1, name="Врата Штейна/Steins;Gate s01e01.mkv", size=10),
        TorrFile(index=2, name="Врата Штейна/Steins;Gate s01e12.mkv", size=20),
    ]

    assert plan.picture.kind == "movie", "симптом не воспроизвёлся: вид уже не фильм"
    assert plan.series is None, "очередь серий у фильма отсутствует по построению"
    chosen = _default_file(plan, plan.ranked[0], files)
    assert chosen.name.endswith("s01e12.mkv"), "фильму - крупнейший файл, а не первая серия"

    marked = pictures(
        [row("Врата Штейна / Steins;Gate [1 сезон: 1-24 серии из 24] (2011) BDRip 1080p", "b")]
    )[0]
    series_plan = plan_for(marked, Args(query=["врата штейна"]), Config())
    assert series_plan.series is not None
    assert _default_file(series_plan, series_plan.ranked[0], files).name.endswith("s01e01.mkv")
