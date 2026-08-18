"""Раздача внешнего мира стенду: те же слоты, что заполняет боевой композиционный корень.

Одну и ту же вещь корень (:func:`torrcast.runtime.wire.wire`) раздаёт нескольким
сценариям сразу: службу раздач - шести, паспорт файла - четырём, завод приёмника -
двум. Стенду нужна ровно та же раздача, только подделкой, поэтому слоты перечислены
здесь поимённо и рядом - как в корне.

⚠️ Прежде это делал плоский namespace прежнего монолита: тест подменял одно имя на
``torrcast.cli``, а мост в ``conftest`` разносил подмену по модулям. Разница не в
многословности, а в честности: слот назван модулем и именем, промах виден глазами, и
никакой продуктовый модуль ради тестов крючков больше не носит.

Подделка приходит сюда как ``Callable[..., object]``, а не портом: стенду он нужен не
целиком - подделка отвечает ровно на то, что меряет тест. Договор слота держит сам
слот, и его тип от этого не слабеет.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from types import ModuleType

import pytest

from torrcast.adapters import choice_environment
from torrcast.usecases import cache_reserve, episode_duration, torrents, voices_command, worker
from torrcast.usecases.cast_command import _play_state
from torrcast.usecases.discover import _search_state
from torrcast.usecases.playback import _show_state
from torrcast.usecases.playback._launch import _await_playing
from torrcast.usecases.rank.peer_grace import peer_grace
from torrcast.usecases.select import _pick_state
from torrcast.usecases.select_bench import _bench_state, _bench_work

#: Что стенд ставит на слот: завод, правило или подделка любой полноты.
StandIn = Callable[..., object]


def _home(unit: object) -> ModuleType:
    """Модуль, в котором единица объявлена.

    ⚠️ Спросить его у пакета нельзя: пакет переэкспортирует единицу ПОД ИМЕНЕМ ЕЁ
    МОДУЛЯ, и ``import torrcast.usecases.rank.peer_grace as ...`` молча отдаёт саму
    функцию вместо модуля - подмена легла бы в никуда. Свой дом единица знает сама.
    """
    home = inspect.getmodule(unit)
    assert home is not None, "у единицы нет дома: сломан импорт"
    return home


#: Правило отсрочки первого контакта и запуск показа: оба - тёзки своих модулей.
_grace_rule = _home(peer_grace)
_launch_show = _home(_await_playing)


def use_engines(patch: pytest.MonkeyPatch, engines: StandIn) -> None:
    """Служба раздач - всем шести сценариям, которым её даёт корень."""
    patch.setattr(cache_reserve, "_reserve_engines", engines)
    patch.setattr(_play_state, "_play_engines", engines)
    patch.setattr(_pick_state, "_select_engines", engines)
    patch.setattr(torrents, "_cleanup_engines", engines)
    patch.setattr(voices_command, "_voices_engines", engines)
    patch.setattr(worker, "_worker_engines", engines)


def use_indexers(patch: pytest.MonkeyPatch, indexers: StandIn) -> None:
    """Завод клиента индексеров: его знает только поиск."""
    patch.setattr(_search_state, "_search_indexers", indexers)


def use_prober(patch: pytest.MonkeyPatch, prober: StandIn) -> None:
    """Паспорт файла - всем четырём сценариям, которым его даёт корень."""
    patch.setattr(episode_duration, "_episode_prober", prober)
    patch.setattr(_show_state, "probe", prober)
    patch.setattr(_pick_state, "_select_prober", prober)
    patch.setattr(_bench_state, "_bench_prober", prober)


def use_receivers(patch: pytest.MonkeyPatch, receivers: StandIn) -> None:
    """Завод приёмника - показу и юниту показа."""
    patch.setattr(_show_state, "make_receiver", receivers)
    patch.setattr(worker, "_worker_receivers", receivers)


def use_warm_file(patch: pytest.MonkeyPatch, warm_file: StandIn) -> None:
    """Прогрев файла: его знает только стенд отбора."""
    patch.setattr(_bench_state, "_bench_warm_file", warm_file)


def use_passport(patch: pytest.MonkeyPatch, passport: StandIn) -> None:
    """Справка о картине - окружению выбора и поиску."""
    patch.setattr(choice_environment, "_passport", passport)
    patch.setattr(_search_state, "_search_passport", passport)


def use_await_playing(patch: pytest.MonkeyPatch, await_playing: StandIn) -> None:
    """Ожидание картинки на экране - модулю запуска показа, который её и ждёт."""
    patch.setattr(_launch_show, "_await_playing", await_playing)


def use_graces(
    patch: pytest.MonkeyPatch, *, peer: float | None = None, step: float | None = None
) -> None:
    """Отсрочки первого контакта - правилу, которое их и назначает.

    Стенд отбора отсрочку не выбирает: он спрашивает её у правила
    (:func:`torrcast.usecases.rank.peer_grace.peer_grace`) на каждую раздачу, поэтому
    подмена ложится в модуль правила, а не в стенд.
    """
    if peer is not None:
        patch.setattr(_grace_rule, "PEER_GRACE", peer)
    if step is not None:
        patch.setattr(_grace_rule, "STEP_GRACE", step)


def use_swarm_grace(patch: pytest.MonkeyPatch, grace: float) -> None:
    """Отсрочка молчащего потока - стенду, который её и спрашивает у признака жизни роя."""
    patch.setattr(_bench_work, "SWARM_GRACE", grace)
