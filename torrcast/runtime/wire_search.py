"""Проводка поиска и отбора раздачи: тут её сценарии видят каталог и службу раздач.

Зовёт её композиционный корень (:func:`torrcast.runtime.wire.wire`), и только он."""

from torrcast.adapters.choice_environment import _configure_choice_environment
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
from torrcast.usecases.cache_reserve import _configure_cache_reserve
from torrcast.usecases.choice.configure import configure as configure_choice
from torrcast.usecases.discover._search_state import _configure_discover
from torrcast.usecases.episode_duration import _configure_episode_duration
from torrcast.usecases.rank._cut import _cut
from torrcast.usecases.rank.bitrate_of import bitrate_of
from torrcast.usecases.rank.configure import configure as configure_rank
from torrcast.usecases.rank.hevc_hope import hevc_hope
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.is_dated import is_dated
from torrcast.usecases.reinforce._timed import _timed
from torrcast.usecases.reinforce.configure import configure as configure_reinforce
from torrcast.usecases.select._pick_state import _configure_select
from torrcast.usecases.select_bench._bench_state import _configure_select_bench
from torrcast.usecases.torrents import _configure_torrents


def wire_search() -> None:
    """Отдать поиску и отбору их внешний мир: каталог раздач, службу раздач и паспорт."""
    # Само окружение выбора - адаптер, и правила соседних сценариев ему не назвать
    # импортом: ранжирование, добор и справка лежат слоем выше адаптеров. Прежде оно
    # доставало их строкой с именем модуля прямо в вызове; называет их теперь корень.
    _configure_choice_environment(
        FACTS.passport.of, _cut, bitrate_of, hevc_hope, is_candidate, is_dated, _timed
    )
    # 🔴 То же и у выбора раздачи: среду раздавал импорт фасада-смертника `torrcast.choice`,
    # и беда пряталась за порядком импортов. Фасада нет, раздаёт корень (TC-630). ⚠️ Слот
    # берётся ИМЕНЕМ ИЗ МОДУЛЯ: у пакета-части плоского namespace короткое `configure`
    # затёрто одноимённой единицей ранжирования, и среда встала бы в никуда, молча.
    configure_choice(choice_environment)
    # И у ранжирования то же: печать ему раздавал импорт совместимого фасада.
    configure_rank(PrintConsole())
    # Медиатракт: службу раздач сценарии заводят сами - адрес и срок ответа знают только
    # они, - но ЧЕМ её заводить, знает отсюда. Иначе имя `TorrServer` появлялось бы в
    # сценарии из строки, и слой показа снова ходил бы в сеть напрямую.
    _configure_cache_reserve(TorrServer)
    _configure_torrents(TorrServer)
    _configure_episode_duration(probe)
    # Стенд отбора греет раздачи параллельно: чтение паспорта, прогрев файла, признак
    # жизни роя и отсрочка первого контакта - четыре разных внешних мира, и все четыре
    # приходят отсюда. Прежде стенд доставал их строкой с именем прежнего фасада.
    _configure_select_bench(probe, warm_file, swarm_pulse, ContactWait)
    # Сам отбор ходит в службу раздач ровно один раз - за дорожками названного
    # вручную релиза, - и спрашивает человека о начале сериала заново. Служба,
    # чтение паспорта и вопрос приходят отсюда, а не из строки с именем фасада.
    _configure_select(TorrServer, probe, ask_line)
    # Поиск: сырая выдача каталога, справка о картинах и завод клиента индексеров. Все
    # трое ходят в сеть, и слою сценариев их не назвать - только корню. Добор берёт первые
    # два тем же порядком: прежде их раздавал импорт фасада-смертника `torrcast.reinforce`,
    # единственного, кто видел сразу `torrcast.adapters.prowlarr` и `torrcast.runtime.facts_wiring`
    # (TC-632). Слот - снова именем из модуля, по причине выше.
    _configure_discover(torrent_catalogue, FACTS.passport.of, Prowlarr)
    configure_reinforce(torrent_catalogue, FACTS.passport.of)
