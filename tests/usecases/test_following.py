"""Зеркало :mod:`torrcast.usecases.following`: серия, которую юнит доиграет следом.

Единица отвечает на один вопрос и отдаёт один ответ, но читают его двое: цикл юнита берёт
отсюда следующую серию, а показ - решение, закрывать ли приложение приёмника. Поэтому
сторожится и то, когда ответ есть, и то, когда его нет: пустой ответ здесь - это конец
показа, а не осечка.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from torrcast.domain.entry import Entry
from torrcast.usecases import following as following_module
from torrcast.usecases.following import _following

KEY = "tv:сериал:2020"


class FakeState(dict[str, Entry]):
    """Состояние как его видит сценарий: словарь записей, который умеет загрузиться."""

    loaded: ClassVar[dict[str, Entry]] = {}

    @classmethod
    def load(cls) -> FakeState:
        return cls(cls.loaded)


@pytest.fixture(autouse=True)
def _state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет внешнее состояние, чтобы вопрос про следующую серию не трогал диск."""
    FakeState.loaded = {}
    monkeypatch.setattr(following_module, "State", FakeState)


def put(**fields: Any) -> Entry:
    """Кладёт в состояние запись под ключом показа и возвращает её."""
    entry = Entry(title="Сериал", magnet="m", **fields)
    FakeState.loaded = {KEY: entry}
    return entry


def series(**fields: Any) -> Entry:
    """Сериал с выбранной раздачей: у записи есть подпись серии."""
    return put(kind="tv", season=1, episode=2, episodes=[[1, 2, 5], [1, 3, 6]], **fields)


def test_a_series_in_the_middle_names_the_episode_the_unit_plays_next() -> None:
    """Есть что играть дальше - запись возвращается целиком, вместе с выбором раздачи.

    Цикл юнита берёт отсюда и магнит, и номер файла: переспрашивать отбор между сериями
    нельзя, иначе стык серий стоил бы человеку полного круга по индексерам.
    """
    entry = series()

    following = _following(KEY)

    assert following is not None
    assert following.label == "s1e2"
    assert following.magnet == entry.magnet


def test_a_film_ends_the_show_instead_of_looking_for_a_next_episode() -> None:
    """У фильма следующей серии нет вовсе, и ответ обязан быть пустым.

    По этому же ответу показ знает, что приложение приёмника пора гасить: между сериями
    оно живёт дальше, а на конце показа - гаснет. Ответь единица чем-нибудь - фильм
    оставлял бы приложение на экране после титров.
    """
    put(pos=100.0, dur=1000.0)

    assert _following(KEY) is None


def test_a_finished_record_is_never_offered_for_another_round() -> None:
    """Досмотренное не доигрывают: последняя серия сезона кончает показ.

    Отдай единица досмотренную запись - юнит пошёл бы играть её заново, и сериал зациклился
    бы на своём конце.
    """
    series(done=True)

    assert _following(KEY) is None


def test_a_record_that_was_never_a_series_gives_nothing_to_continue() -> None:
    """Одна серия в раздаче - осечка разбора, а не сериал.

    Так в состоянии осела картина, которую разбор имени сделал первой серией. Прими её
    единица за сериал - показ фильма кончался бы попыткой перейти на несуществующую вторую
    серию.
    """
    put(kind="tv", season=1, episode=1, episodes=[[1, 1, 0]])

    assert _following(KEY) is None


def test_an_unknown_key_is_an_empty_answer_and_not_a_crash() -> None:
    """Записи под ключом может не быть - состояние чистят, и это законно.

    Упади единица здесь - юнит умирал бы на стыке серий вместо того, чтобы честно
    закончить показ.
    """
    FakeState.loaded = {}

    assert _following("tv:такого-нет:1900") is None
