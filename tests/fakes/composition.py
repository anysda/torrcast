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
from torrcast.adapters.filesystem.trace_journal import writer as _tape_slot
from torrcast.ports.clock import Clock
from torrcast.ports.console import Console
from torrcast.ports.health_environment import HealthEnvironment
from torrcast.usecases import (
    cache_reserve,
    doctor_environment,
    episode_duration,
    releases_command,
    torrents,
    voices_command,
    worker,
)
from torrcast.usecases.cast_command import _play_state
from torrcast.usecases.discover import _search_state
from torrcast.usecases.playback import _show_state
from torrcast.usecases.playback._launch import _await_playing
from torrcast.usecases.rank.configure import configure as _rank_configure
from torrcast.usecases.rank.peer_grace import peer_grace
from torrcast.usecases.reinforce.configure import configure as _reinforce_configure
from torrcast.usecases.revive_playback import _revive_state
from torrcast.usecases.select import _pick_state
from torrcast.usecases.select_bench import _bench_state, _bench_work

#: Что стенд ставит на слот: завод, правило или подделка любой полноты.
StandIn = Callable[..., object]


def _home(unit: object) -> ModuleType:
    """Модуль, в котором единица объявлена.

    Свой дом единица знает сама, и спрашивается он у неё. Пакет тут не спрашивается
    намеренно: пока пакеты раздавали имена своих модулей, ``import
    torrcast.usecases.rank.peer_grace as ...`` молча отдавал саму функцию вместо модуля и
    подмена ложилась в никуда. Реэкспорта в usecases больше нет, но у самой единицы
    ответ верен при любой раскладке.
    """
    home = inspect.getmodule(unit)
    assert home is not None, "у единицы нет дома: сломан импорт"
    return home


#: Правило отсрочки первого контакта, запуск показа и слоты добора: все - тёзки
#: своих модулей, и дом у каждого спрашивается у самой единицы.
_grace_rule = _home(peer_grace)
_launch_show = _home(_await_playing)
_reinforce_ports = _home(_reinforce_configure)


def use_tape(patch: pytest.MonkeyPatch, put: StandIn) -> None:
    """Приёмник записей ленты: его знает единственная дверь в след (:func:`emit`).

    Слот лежит у фонового писателя, потому что схема события ловится ровно там, где
    запись уходит в очередь: файл ленты пишет отдельный поток, и его расписание к схеме
    отношения не имеет.
    """
    patch.setattr(_tape_slot, "_tape", put)


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


def use_media_grid(patch: pytest.MonkeyPatch, grid_for: StandIn) -> None:
    """Сетка сегментов файла - показу: тем же слотом, что заполняет корень.

    Сетку показ и прогрев считают одной и той же функцией и обязаны получить одно и то
    же (:func:`torrcast.usecases.playback.layout.layout`), поэтому слот один.
    """
    patch.setattr(_show_state, "grid_for", grid_for)


def use_swarm_grace(patch: pytest.MonkeyPatch, grace: float) -> None:
    """Отсрочка молчащего потока - стенду, который её и спрашивает у признака жизни роя."""
    patch.setattr(_bench_work, "SWARM_GRACE", grace)


def use_profile(patch: pytest.MonkeyPatch, detect: StandIn) -> None:
    """Паспорт приёмника - всем четырём сценариям, которым его даёт корень.

    Спрашивают его показ, команда показа, список релизов и юнит показа: от профиля
    зависят и потолки отбора, и то, какой кодек считается играбельным.
    """
    patch.setattr(_show_state, "detect_profile", detect)
    patch.setattr(_play_state, "_play_detect", detect)
    patch.setattr(releases_command, "_releases_detect", detect)
    patch.setattr(worker, "_worker_detect", detect)


def use_settings(patch: pytest.MonkeyPatch, settings: StandIn) -> None:
    """Файл настроек - всем четырём сценариям, которым его даёт корень."""
    patch.setattr(_play_state, "_play_settings", settings)
    patch.setattr(releases_command, "_releases_settings", settings)
    patch.setattr(voices_command, "_voices_settings", settings)
    patch.setattr(worker, "_worker_configs", settings)


def use_facts(patch: pytest.MonkeyPatch, facts: StandIn) -> None:
    """Справка к меню - обоим сценариям, которым её даёт корень: показу и списку релизов."""
    patch.setattr(_play_state, "_play_facts", facts)
    patch.setattr(releases_command, "_releases_facts", facts)


def use_hls_base(patch: pytest.MonkeyPatch, base: StandIn) -> None:
    """Свой адрес в сторону телевизора: его знает показ, и только он."""
    patch.setattr(_show_state, "hls_base", base)


def use_start_unit(patch: pytest.MonkeyPatch, start: StandIn) -> None:
    """Запуск юнита показа: его зовёт старт показа, и только он.

    Настоящий поднимает systemd на хозяйской машине, поэтому подделка тут не удобство,
    а запрет - ровно как у порта юнита (фикстура ``show_unit``).
    """
    patch.setattr(_show_state, "start_play_unit", start)


def use_revive_clock(patch: pytest.MonkeyPatch, clock: Clock) -> None:
    """Часы оживления показа: по ним меряются темнота и круг опроса приёмника.

    С боевыми часами зеркало ждало бы настоящие секунды на каждом шаге круга, то есть
    меряло бы терпеливость машины вместо решения показа. Часы приходят сюда портом, а
    не подделкой любой полноты: у них есть свой договор, и слабее он не становится.
    """
    patch.setattr(_revive_state, "_revive_clock", clock)


def use_playing_mark(patch: pytest.MonkeyPatch, mark: StandIn) -> None:
    """Отметка «картинка на экране»: её кладёт оживление показа, и только оно."""
    patch.setattr(_revive_state, "_revive_playing_mark", mark)


def blank_reinforce_ports(patch: pytest.MonkeyPatch) -> None:
    """Слоты каталога и справки у добора - пустыми: их ставит корень, и зеркало
    :func:`~torrcast.usecases.reinforce.configure.configure` обязано начинать с чистых.

    ⚠️ Промах имени тут молчал бы дважды. Слота ДО первого вызова нет вовсе (он только
    объявлен типом), поэтому подмена ставится с ``raising=False`` - и переименуйся слот,
    она легла бы в никуда, а зеркало осталось бы зелёным на грязных слотах соседа.
    Отсюда сверка с объявлением модуля: переименование валит зеркало громко.
    """
    for name in ("_catalogue", "_passport_source"):
        assert name in _reinforce_ports.__annotations__, f"слот {name} переименован"
        patch.setattr(_reinforce_ports, name, None, raising=False)


#: Слот консольного порта правил ранжирования: тот же трюк с домом, что у отсрочки и у
#: добора - пакет ``rank`` переэкспортирует ``configure`` ПОД ИМЕНЕМ ЕЁ МОДУЛЯ.
_rank_ports = _home(_rank_configure)


def _slot(patch: pytest.MonkeyPatch, home: ModuleType, name: str, put: object) -> None:
    """Поставить слот по имени, назвав промах вслух.

    ⚠️ Ставится с ``raising=False``: до слова корня имени в модуле нет вовсе - слот там
    только объявлен типом. Поэтому промах имени молчал бы, и зеркало осталось бы зелёным
    на пустом слоте. Ловит его сверка с объявлением модуля: переименуйся слот -
    подстановка упадёт громко и в одном месте, а не разойдётся по зеркалам.
    """
    assert name in home.__annotations__, f"слот {name} переименован в {home.__name__}"
    patch.setattr(home, name, put, raising=False)


def use_rank_console(patch: pytest.MonkeyPatch, console: Console) -> None:
    """Консольный порт правил ранжирования: его ставит корень, и он один на весь пакет.

    Спрашивает его меню дорожек (:func:`~torrcast.usecases.rank.pick_voice.pick_voice`)
    через :func:`~torrcast.usecases.rank.configure._console_port`. Приходит он сюда портом, а не
    подделкой любой полноты: у консоли есть свой договор, и слабее он не становится.
    """
    _slot(patch, _rank_ports, "_console", console)


def blank_rank_console(patch: pytest.MonkeyPatch) -> None:
    """Слот консольного порта - пустым: зеркало самого слова корня обязано начинать с
    чистого, иначе оно мерило бы порт, оставленный соседом."""
    _slot(patch, _rank_ports, "_console", None)


def use_health_environment(patch: pytest.MonkeyPatch, environment: HealthEnvironment) -> None:
    """Системная среда самопроверки: её кладёт композиция
    (:func:`torrcast.usecases.doctor._configure`), а читают пробы и обе мерки машины -
    место у среды одно на всех (:mod:`torrcast.usecases.doctor_environment`).
    """
    _slot(patch, doctor_environment, "environment", environment)
