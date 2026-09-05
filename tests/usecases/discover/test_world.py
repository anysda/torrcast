"""Мир зеркал круга поиска: что ``wire_catalogue`` обязана развести одним вызовом.

Щуп вне pytest зовёт её одну - и лестница добора обязана дойти до конца, а не
упасть на незанятом слоте (``NameError: _catalogue -> _environment ->
RuntimeError: no state store assigned``, TC-1057).
"""

from __future__ import annotations

from tests.usecases.discover.world import Catalogue, wire_catalogue
from torrcast.adapters import choice_environment as _choice_slots
from torrcast.adapters.choice_environment import environment as choice_environment
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.reinforce.configure import _catalogue_port, _passport_port


def test_the_reinforce_slots_hold_the_worlds_own_catalogue_and_passport() -> None:
    """Ступени добора держат свой каталог и справку отдельно от поиска - и получают их тут.

    Сессионная сборка ставит в эти слоты боевой каталог, поэтому тождество с
    заготовкой мира доказывает: развела именно ``wire_catalogue``, а не фикстура.
    """
    wire_catalogue()

    assert isinstance(_catalogue_port(), Catalogue)
    assert _passport_port()("харли квинн") == Origin(), "справка мира молчит, а не выдумывает"


def test_the_choice_environment_is_occupied_and_answers_the_ladder() -> None:
    """Живость и годность раздач считает окружение выбора: слот занят и отвечает.

    Сам слот внутри набора уже занят сессионной сборкой, поэтому сверяется не его
    занятость, а ДОВОД: справка адаптера обязана быть мировой, молчащей - иначе
    щуп вне pytest получил бы её ``NameError``'ом (звено ``_environment``).
    """
    wire_catalogue()

    assert _environment_port() is choice_environment
    assert _environment_port().alive_seeders > 0
    assert _choice_slots._passport.__qualname__ == "wire_catalogue.<locals>.passport_of"
