"""Английские надписи кластера самопроверки."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера самопроверки.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "health.ok": "ok      {text}",
        "health.warn": "warning {text}",
        "health.bad": "bad     {text}",
        "health.gib": "{size:.1f} GiB",
        "health.server_silent": "TorrServer is silent ({url}) - nothing will be served",
        "health.cache_unreadable": (
            "TorrServer settings are unreadable - the cache size is unknown"
        ),
        "health.cache_in_memory": (
            "serving cache {size} in memory, which costs about {weight} of the "
            "machine's {total} while playing"
        ),
        "health.cache_no_room": (
            "{text} - it does not fit: playback will take the machine down, rerun install.sh"
        ),
        "health.cache_on_disk": "serving cache {size} on disk ({path})",
        "health.cache_path_unset": "path not set",
        "health.cache_path_loose": (
            "{text} - the service will put it wherever it likes, rerun install.sh"
        ),
        "health.cache_free_unknown": "{text}, free space on the partition is unreadable",
        "health.cache_disk_room": "{text}, service memory about {memory}, {free} on the partition",
        "health.cache_no_warm_room": (
            "{text} - no room left for warmup, a dropout will cut playback short"
        ),
        "health.no_terminal": "no terminal (non-interactive run) - questions will take defaults",
        "health.terminal_mode_unknown": (
            "a terminal is here, but its input mode is unreadable - non-ASCII input is unchecked"
        ),
        "health.iutf8_on": "already on",
        "health.iutf8_off": "off, we turn it on for the length of the command",
        "health.terminal_ok": (
            "terminal: pty is here, IUTF8 {how} - non-ASCII answers will type through"
        ),
        "health.locale_ok": "locale: {encoding} {env}",
        "health.locale_bad": "locale {encoding} is not UTF-8 - names will be mangled ({env})",
        "health.locale_empty": "empty",
        "health.no_ffmpeg": "ffmpeg does not run - there is nothing to pack the stream with",
        "health.ffmpeg_no_burst": "{head}: no -readrate_initial_burst - the start will be slow",
        "health.ffmpeg_ok": "{head}, -readrate_initial_burst is there",
        "health.prowlarr_unit_unknown": (
            "the Prowlarr service is not ours to manage - which route it takes to the "
            "trackers is out of sight"
        ),
        "health.prowlarr_ipv4": (
            "Prowlarr reaches the trackers over IPv4 - over IPv6 their answers get cut short"
        ),
        "health.prowlarr_ipv6": (
            "Prowlarr may reach a tracker over IPv6, where answers get cut short - the "
            "indexer goes quiet, and it looks exactly like an empty search; the cure is "
            "the line “{knob}” in its unit (the installer puts it there)"
        ),
        "health.prowlarr_no_apikey": (
            "Prowlarr: the apikey is empty - nothing to search with, rerun ./install.sh"
        ),
        "health.prowlarr_silent": "Prowlarr is silent ({url}) - there will be no search",
        "health.prowlarr_no_indexers": "Prowlarr answers, but has zero indexers ({url})",
        "health.prowlarr_indexers": "Prowlarr answers, indexers {count} ({url})",
        "health.indexer_paused": "indexer {name} is disabled by Prowlarr until {till}",
        "health.indexer_answered": "indexer {name} answered a live search",
        "health.indexer_irrelevant": (
            "indexer {name} answered beside the control query - its results are unreliable"
        ),
        "health.indexer_silent": (
            "indexer {name} did not answer a live search - results will be short"
        ),
        "health.core_present": "{indexer} is in place - {gives} are in the catalogue",
        "health.core_absent": (
            "{indexer} is missing or switched off - search still runs, but there will be "
            "noticeably fewer {misses} in the results; bring it back with ./install.sh"
        ),
        "health.core_gives_west": "western releases and anime",
        "health.core_misses_west": "western releases and anime",
        "health.core_gives_russian": "Russian releases and dubs",
        "health.core_misses_russian": "Russian releases and dubs",
        "health.tv_unnamed": (
            "the TV address is not set: cast --tv (finds receivers by itself) or cast --tv <ip>"
        ),
        "health.tv_mock": "receiver mock ({tv}) - nothing is cast outside, this is test mode",
        "health.tv_no_route": "no route to TV {tv} - the cast will not go through",
        "health.tv_route": "TV {tv} is visible from our leg {ours}",
        "health.tv_port_shut": "port {port} on the TV did not open ({error}) - TV unplugged?",
        "health.tv_port_open": "port {port} on the TV is open - the receiver will take the show",
        "health.tv_no_info": (
            "the receiver told us nothing about itself - uptime and link are unknown"
        ),
        "health.link_wired": "by cable",
        "health.link_wifi": "over Wi-Fi",
        "health.link_unnamed": "link not named",
        "health.tv_link": "receiver connected {link}",
        "health.tv_uptime": "receiver up {uptime}, connected {link}",
        "health.mdns_heard": (
            "mDNS: heard {count} receivers ({names}) - search will have names to show"
        ),
        "health.tv_profile": "receiver profile: {title} - {how}",
        "health.tv_profile_by_hand": (
            "{text}; to name it by hand use the receiver_profile key in the config"
        ),
        "health.hls_no_base": "the serving address does not add up: {error}",
        "health.hls_plain": "serving {base} - no certificate and no DNS on the playback path",
        "health.hls_cert_unreadable": "serving {base}, but certificate {cert} is unreadable",
        "health.hls_cert_expiring": (
            "serving {base}, {days} days left on the certificate - playback is about to break"
        ),
        "health.hls_cert_ok": "serving {base}, {days} days left on the certificate",
        "health.shelves": (
            "shelves in {shelf}: keyframe maps {keys}/{keys_kept} ({keys_mb:.1f} MB), "
            "media probes {probe}/{probe_kept} ({probe_mb:.1f} MB)"
        ),
        "health.ago_minutes": "{count:.0f} min",
        "health.ago_hours": "{count:.0f} h",
        "health.ago_days": "{count:.0f} d",
        "health.trace_missing": "no trace in {directory} - `cast log` will show nothing",
        "health.trace_size": "{size:.1f} MB",
        "health.trace_stale": "trace is there ({size}), but the last record is {days:.0f} days old",
        "health.trace_ok": "trace {size}, last record {ago} ago",
    }
