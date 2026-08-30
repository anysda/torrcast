"""Зеркало подготовки релиза: пока фаза не прошла, спрашивать её результат нечем."""

from __future__ import annotations

import pytest

from tests.usecases.select.world import release
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.select._prep import _Prep


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские отказы подготовки релиза, не дошедшей до результата."""


def _prep() -> _Prep:
    return _Prep(number=1, release=release())


def test_a_fresh_preparation_stands_in_the_queue_and_promises_nothing() -> None:
    """Умолчания - это «ещё ничего не было»: ни файла, ни паспорта, ни отказа."""
    prep = _prep()

    assert prep.phase == "очередь"
    assert (prep.video, prep.media, prep.error, prep.failure) == (None, None, "", None)
    assert prep.ready.is_set() is False


def test_asking_for_a_file_that_was_never_picked_is_an_infra_failure() -> None:
    """Молчаливого ``None`` наружу не бывает: не выбран - значит поломка, а не пусто."""
    with pytest.raises(InfraError, match="файл раздачи не выбран"):
        assert _prep().want


def test_asking_for_a_stream_that_was_never_read_is_an_infra_failure() -> None:
    """То же и с паспортом потока: не прочитан - это поломка звена, а не ответ."""
    with pytest.raises(InfraError, match="поток не прочитан"):
        assert _prep().found


def test_what_the_phases_put_there_is_what_is_asked_back() -> None:
    """Фазы идут своим ходом, а показ спрашивает только результат."""
    prep = _prep()
    prep.video = TorrFile(index=2, name="кино.mkv", size=1)
    prep.media = Media(duration=7200.0)

    assert prep.want.index == 2
    assert prep.found.duration == 7200.0


def test_the_timing_names_both_budgets_the_preparation_spent() -> None:
    """Сколько стоила подготовка - это две цифры, и обе называются человеку."""
    prep = _prep()
    prep.meta, prep.read = 1.25, 17.0

    assert prep.timing == "метаданные 1.2 с, дорожки 17.0 с"
