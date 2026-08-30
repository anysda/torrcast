"""Английский каталог кластера ``chromecast_talk``: он же умолчание, он же запасной."""

from __future__ import annotations


def en() -> dict[str, str]:
    return {
        "chromecast_talk.no_status": "no status",
        "chromecast_talk.with_code": ", with code {code}",
        "chromecast_talk.without_code": ", without a code",
        "chromecast_talk.tv_did_not_start": "TV {address} did not start the show: {reason}",
        "chromecast_talk.tv_rejected_cast": "TV {address} did not accept the cast: {reason}",
        "chromecast_talk.tv_no_reconnect_answer": (
            "TV {address} did not answer the reconnect: {reason}"
        ),
        "chromecast_talk.no_tv_address": (
            "no TV address set: cast --tv will find televisions on the network"
        ),
        "chromecast_talk.receiver_stuck": (
            "receiver got stuck - closing the app and the connection, reloading"
        ),
        "chromecast_talk.load_not_taken": (
            "LOAD was not taken ({reason}) - retry {tries} of {limit}"
        ),
        "chromecast_talk.receiver_dropped": (
            "receiver dropped at {position} s{reason} - retrying LOAD"
        ),
        "chromecast_talk.dying_on_one_chunk": (
            "the show keeps dying on the same chunk (attempt {count}) - skipping it, "
            "{gap} s of film missed ({start} s -> {end} s)"
        ),
        "chromecast_talk.nudges_gave_no_frame": (
            "nudges gave no frame ({count} in a row) - stopping the jumps, "
            "the show will resume from the last frame shown"
        ),
        "chromecast_talk.nudge_interrupted": "guard interrupted with a nudge",
        "chromecast_talk.session_broke": "session broke off",
        "chromecast_talk.another_seek_arrived": "another seek arrived right after",
        "chromecast_talk.reconnect_timeout": (
            "TV {address} has been reconnecting for over {timeout} s - "
            "{what} did not go through: {reason}"
        ),
        "chromecast_talk.reconnect_wait": (
            "receiver's socket is reconnecting - waiting up to {timeout} s for {what}"
        ),
        "chromecast_talk.stalled_skip": (
            "receiver was stalling - the show skipped {gap} s of film "
            "({start} s -> {end} s)"
        ),
        "chromecast_talk.refused_busy": "refused: receiver is busy with someone else's show",
        "chromecast_talk.refused_crashed": "crashed: {reason}",
        "chromecast_talk.refused_not_taken": (
            "not taken: LOAD went through but no picture came"
        ),
        "chromecast_talk.refused_decoder_died": (
            "not taken: decoder died before starting the show"
        ),
        "chromecast_talk.refused_no_show_set": "refused: no show was ever loaded here",
        "chromecast_talk.refused_sulking": (
            "refused: receiver remembers a 404 and will not take LOAD"
        ),
        "chromecast_talk.manifest_not_fetched": "receiver did not fetch the manifest: {reason}",
        "chromecast_talk.cors_header_missing": (
            "response has no {header}: * - Chromecast silently refuses to play that"
        ),
    }
