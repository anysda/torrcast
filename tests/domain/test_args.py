"""Разобранная строка сама называет свою команду, серию и режим отладки."""

from __future__ import annotations

import pytest

from torrcast.domain.args import Args
from torrcast.domain.episode import Episode


@pytest.mark.parametrize("word", ["stop", "status", "doctor", "releases", "voices", "log"])
def test_a_command_word_in_the_query_names_the_command(word: str) -> None:
    assert Args(query=[word]).command == word


def test_an_empty_query_is_status_and_with_an_address_it_is_configuration() -> None:
    """Пустой запрос - это «что играет»; пустой запрос с ``--tv`` - установка."""
    assert Args(query=[]).command == "status"
    assert Args(query=[], tv="10.0.0.50").command == "configure"
    assert Args(query=[], tv="?").command == "configure"


def test_a_play_key_outranks_everything_else() -> None:
    """Внутренний ключ показа зовётся юнитом, и спорить с ним словам запроса нечем."""
    assert Args(query=["stop"], play_key="movie:кино:1999").command == "worker"


def test_a_title_is_the_show_command() -> None:
    assert Args(query=["моана", "2"]).command == "play"


def test_the_episode_is_split_off_the_title() -> None:
    """Искать надо «киберпанк», а не «киберпанк 2x5»: серия - отдельное поле."""
    args = Args(query=["киберпанк", "s2e5"])

    assert args.episode == Episode(2, 5)
    assert args.title_query == "киберпанк"


def test_a_query_without_an_episode_keeps_its_whole_title() -> None:
    args = Args(query=["моана", "2"])

    assert args.episode is None
    assert args.title_query == "моана 2"


def test_a_hand_named_release_or_file_is_the_debug_path() -> None:
    """Релиз или файл названы руками - подмен на этом пути не бывает."""
    assert not Args(query=["кино"]).pinned
    assert Args(query=["кино"], release=2).pinned
    assert Args(query=["кино"], file=1).pinned
    assert not Args(query=["кино"], voice=3).pinned, "озвучка выбор раздачи не прибивает"


def test_a_menu_asked_by_hand_outranks_the_bookmark() -> None:
    """``--menu`` и ``--pick N`` называют картину сами - место в записи им не ответ."""
    assert not Args(query=["кино"]).from_menu
    assert Args(query=["кино"], menu=True).from_menu
    assert Args(query=["кино"], pick=3).from_menu
    assert not Args(query=["кино"], release=2).from_menu, "релиз - это раздача, не картина"
