"""Надпись по ключу на языке человека, со значениями, подставленными по имени.

Каталоги распределены по кластерам продукта: у каждого кластера своя пара файлов
``ru.py`` / ``en.py``, и растёт список кластеров, а не один файл на весь продукт.
Английский тут одновременно язык по умолчанию и запасной каталог: ключ, которого в
русском ещё нет, отвечает по-английски, а не пустотой и не ключом.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.catalogs.choice.en import en as choice_en
from torrcast.domain.catalogs.choice.ru import ru as choice_ru
from torrcast.domain.catalogs.chromecast_scan.en import en as chromecast_scan_en
from torrcast.domain.catalogs.chromecast_scan.ru import ru as chromecast_scan_ru
from torrcast.domain.catalogs.chromecast_talk.en import en as chromecast_talk_en
from torrcast.domain.catalogs.chromecast_talk.ru import ru as chromecast_talk_ru
from torrcast.domain.catalogs.cli.en import en as cli_en
from torrcast.domain.catalogs.cli.ru import ru as cli_ru
from torrcast.domain.catalogs.console.en import en as console_en
from torrcast.domain.catalogs.console.ru import ru as console_ru
from torrcast.domain.catalogs.digest.en import en as digest_en
from torrcast.domain.catalogs.digest.ru import ru as digest_ru
from torrcast.domain.catalogs.discover.en import en as discover_en
from torrcast.domain.catalogs.discover.ru import ru as discover_ru
from torrcast.domain.catalogs.frames.en import en as frames_en
from torrcast.domain.catalogs.frames.ru import ru as frames_ru
from torrcast.domain.catalogs.health.en import en as health_en
from torrcast.domain.catalogs.health.ru import ru as health_ru
from torrcast.domain.catalogs.http_server.en import en as http_server_en
from torrcast.domain.catalogs.http_server.ru import ru as http_server_ru
from torrcast.domain.catalogs.hunt.en import en as hunt_en
from torrcast.domain.catalogs.hunt.ru import ru as hunt_ru
from torrcast.domain.catalogs.main_config.en import en as main_config_en
from torrcast.domain.catalogs.main_config.ru import ru as main_config_ru
from torrcast.domain.catalogs.media_binaries.en import en as media_binaries_en
from torrcast.domain.catalogs.media_binaries.ru import ru as media_binaries_ru
from torrcast.domain.catalogs.playback.en import en as playback_en
from torrcast.domain.catalogs.playback.ru import ru as playback_ru
from torrcast.domain.catalogs.playback_session.en import en as playback_session_en
from torrcast.domain.catalogs.playback_session.ru import ru as playback_session_ru
from torrcast.domain.catalogs.ports.en import en as ports_en
from torrcast.domain.catalogs.ports.ru import ru as ports_ru
from torrcast.domain.catalogs.profile_detector.en import en as profile_detector_en
from torrcast.domain.catalogs.profile_detector.ru import ru as profile_detector_ru
from torrcast.domain.catalogs.prowlarr.en import en as prowlarr_en
from torrcast.domain.catalogs.prowlarr.ru import ru as prowlarr_ru
from torrcast.domain.catalogs.rank.en import en as rank_en
from torrcast.domain.catalogs.rank.ru import ru as rank_ru
from torrcast.domain.catalogs.receiver.en import en as receiver_en
from torrcast.domain.catalogs.receiver.ru import ru as receiver_ru
from torrcast.domain.catalogs.recode.en import en as recode_en
from torrcast.domain.catalogs.recode.ru import ru as recode_ru
from torrcast.domain.catalogs.revive.en import en as revive_en
from torrcast.domain.catalogs.revive.ru import ru as revive_ru
from torrcast.domain.catalogs.runtime.en import en as runtime_en
from torrcast.domain.catalogs.runtime.ru import ru as runtime_ru
from torrcast.domain.catalogs.screen.en import en as screen_en
from torrcast.domain.catalogs.screen.ru import ru as screen_ru
from torrcast.domain.catalogs.select.en import en as select_en
from torrcast.domain.catalogs.select.ru import ru as select_ru
from torrcast.domain.catalogs.select_bench.en import en as select_bench_en
from torrcast.domain.catalogs.select_bench.ru import ru as select_bench_ru
from torrcast.domain.catalogs.series.en import en as series_en
from torrcast.domain.catalogs.series.ru import ru as series_ru
from torrcast.domain.catalogs.spans.en import en as spans_en
from torrcast.domain.catalogs.spans.ru import ru as spans_ru
from torrcast.domain.catalogs.stream.en import en as stream_en
from torrcast.domain.catalogs.stream.ru import ru as stream_ru
from torrcast.domain.catalogs.stream_pack.en import en as stream_pack_en
from torrcast.domain.catalogs.stream_pack.ru import ru as stream_pack_ru
from torrcast.domain.catalogs.stream_probe.en import en as stream_probe_en
from torrcast.domain.catalogs.stream_probe.ru import ru as stream_probe_ru
from torrcast.domain.catalogs.systemd.en import en as systemd_en
from torrcast.domain.catalogs.systemd.ru import ru as systemd_ru
from torrcast.domain.catalogs.telegram_config.en import en as telegram_config_en
from torrcast.domain.catalogs.telegram_config.ru import ru as telegram_config_ru
from torrcast.domain.catalogs.tongue import RU, tongue
from torrcast.domain.catalogs.torrserver.en import en as torrserver_en
from torrcast.domain.catalogs.torrserver.ru import ru as torrserver_ru
from torrcast.domain.catalogs.trace.en import en as trace_en
from torrcast.domain.catalogs.trace.ru import ru as trace_ru

#: Кластеры каталога: (английский, русский). Заход перевода добавляет сюда строку -
#: пару файлов своего кластера, - а не правит эту функцию. Строка на кластер и запятая
#: в конце: так соседний заход добавляет свой кластер, не трогая ничьей чужой строки.
_CLUSTERS: Final = (
    (choice_en, choice_ru),
    (cli_en, cli_ru),
    (digest_en, digest_ru),
    (discover_en, discover_ru),
    (frames_en, frames_ru),
    (health_en, health_ru),
    (hunt_en, hunt_ru),
    (rank_en, rank_ru),
    (receiver_en, receiver_ru),
    (select_bench_en, select_bench_ru),
    (select_en, select_ru),
    (series_en, series_ru),
    (spans_en, spans_ru),
    (stream_en, stream_ru),
    (trace_en, trace_ru),
    (telegram_config_en, telegram_config_ru),
    (ports_en, ports_ru),
    (profile_detector_en, profile_detector_ru),
    (runtime_en, runtime_ru),
    (chromecast_talk_en, chromecast_talk_ru),
    (media_binaries_en, media_binaries_ru),
    (stream_pack_en, stream_pack_ru),
    (stream_probe_en, stream_probe_ru),
    (main_config_en, main_config_ru),
    (playback_session_en, playback_session_ru),
    (chromecast_scan_en, chromecast_scan_ru),
    (console_en, console_ru),
    (http_server_en, http_server_ru),
    (prowlarr_en, prowlarr_ru),
    (recode_en, recode_ru),
    (systemd_en, systemd_ru),
    (torrserver_en, torrserver_ru),
    (revive_en, revive_ru),
    (playback_en, playback_ru),
    (screen_en, screen_ru),
)


def phrase(key: str, **values: object) -> str:
    """Собрать надпись: ключ + значения по имени, на языке из :func:`tongue`."""
    english: dict[str, str] = {}
    spoken: dict[str, str] = {}
    for in_english, in_russian in _CLUSTERS:
        english.update(in_english())
        spoken.update(in_russian() if tongue() == RU else in_english())
    return spoken.get(key, english[key]).format(**values)
