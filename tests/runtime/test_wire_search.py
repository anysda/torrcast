"""Проводка поиска и отбора: после неё в слотах стоят настоящий каталог и служба раздач."""

from __future__ import annotations

import torrcast.adapters.choice_environment as _choice_slots
import torrcast.usecases.cache_reserve as _cache_reserve
import torrcast.usecases.choice.configure as _choice_configure
import torrcast.usecases.discover._search_state as _search_state
import torrcast.usecases.episode_duration as _episode_duration
import torrcast.usecases.rank.configure as _rank_configure
import torrcast.usecases.reinforce.configure as _reinforce_configure
import torrcast.usecases.select._pick_state as _pick_state
import torrcast.usecases.select_bench._bench_state as _bench_state
import torrcast.usecases.torrents as torrents
from torrcast.adapters.choice_environment import environment as choice_environment
from torrcast.adapters.console.console.ask_line import ask_line
from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.adapters.stream_pack.warm_file import warm_file
from torrcast.adapters.stream_probe.probe import probe
from torrcast.adapters.stream_probe.swarm_pulse import swarm_pulse
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.wire_search import wire_search
from torrcast.usecases.rank._cut import _cut
from torrcast.usecases.rank.bitrate_of import bitrate_of
from torrcast.usecases.rank.hevc_hope import hevc_hope
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.is_dated import is_dated
from torrcast.usecases.reinforce._timed import _timed


def test_the_search_gets_the_real_catalogue_and_the_real_release_service() -> None:
    """Каждый слот поиска и отбора занят ТЕМ САМЫМ адаптером, а не однофамильцем.

    Живое приложение проводит поиск на запуске (``tests.conftest._wired``), поэтому
    повторный вызов тут только подтверждает: слот берёт своё значение отсюда.

    🔴 Сверяется САМО значение, а не то, что его можно позвать: пустышка нужной арности
    договору порта отвечает не хуже настоящего адаптера. Ручка справки
    (``FACTS.passport.of``) собирается заново на каждое обращение, поэтому сверяется
    через ``==``: у связанного метода равенство - это тот же ``__self__`` и та же
    ``__func__``, а ``is`` не держал бы и настоящее значение.

    Полноту этого списка держит не память, а сторож гейта (``scripts/test-gate``): он
    сам сличает доводы, которые кладёт :func:`wire_search`, с тем, что сверяет зеркало,
    и новый слот без сверки по значению не пропустит.
    """
    wire_search()

    # Окружение выбора: правила соседних сценариев и само окружение.
    assert _choice_slots._passport == FACTS.passport.of
    assert _choice_slots._cut is _cut
    assert _choice_slots._bitrate_of is bitrate_of
    assert _choice_slots._hevc_hope is hevc_hope
    assert _choice_slots._is_candidate is is_candidate
    assert _choice_slots._is_dated is is_dated
    assert _choice_slots._timed is _timed
    assert _choice_configure._environment is choice_environment
    assert type(_rank_configure._console) is PrintConsole

    # Служба раздач и паспорт потока: запас кэша, уборка и длительность серии.
    assert _cache_reserve._reserve_engines is TorrServer
    assert torrents._cleanup_engines is TorrServer
    assert _episode_duration._episode_prober is probe

    # Стенд отбора и сам отбор.
    assert _bench_state._bench_prober is probe
    assert _bench_state._bench_warm_file is warm_file
    assert _bench_state._bench_swarm_pulse is swarm_pulse
    assert _bench_state._bench_contact_wait is ContactWait
    assert _pick_state._select_engines is TorrServer
    assert _pick_state._select_prober is probe
    assert _pick_state._select_ask_line is ask_line

    # Поиск и добор: сырая выдача каталога, справка и завод клиента индексеров.
    assert _search_state._search_catalogue is torrent_catalogue
    assert _search_state._search_passport == FACTS.passport.of
    assert _search_state._search_indexers is Prowlarr
    assert _reinforce_configure._catalogue is torrent_catalogue
    assert _reinforce_configure._passport_source == FACTS.passport.of
