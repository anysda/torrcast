"""Английские надписи кластера подъёма погасшего показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера подъёма показа.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "revive.screen_dark": "show went dark at {pos}",
        "revive.no_frame_yet": "not a single frame shown yet (started from {pos})",
        "revive.will_raise": "{said} ({why}) - I will bring it back myself once the network returns",
        "revive.give_up": (
            "could not bring the show back ({tries} tries, dark for {dark} s) - "
            "giving up; cast will resume from {pos}"
        ),
        "revive.receiver_silent": "the receiver went silent",
        "revive.network_back": "the network is back",
        "revive.raising": "{came} - bringing the show back from {pos} (attempt {tries})",
        "revive.raised": "the show is back up from {pos}",
        "revive.no_reason_given": "no reason given",
        "revive.refused": "the receiver refused the show ({why}) - still waiting",
        "revive.picture_started": "{tag} picture started at {pos}",
        "revive.trace_line": (
            "{tag} margin: shown {pos} · packed {packed} · ahead {ahead} s · "
            "{mb} MB · drift from manifest {drift} s · {state}"
        ),
        "revive.tries_so_far": "raised {tries} out of {limit}",
        "revive.source_not_back": "the source has not returned - leaving the receiver alone",
        "revive.dark_report": "{tag} dark for {dark} ({why}) - no picture; {spent}, giving up in {left}",
        "revive.no_network": "no network ({why}) - show is covered until {until}",
        "revive.pause_from_remote": "paused from the remote - stopping the pack",
        "revive.pause_session_lost": (
            "the receiver lost the paused session - returning the show to {pos}; "
            "it will not resume on its own"
        ),
        "revive.pause_restored": "the show is back at {pos}, paused - waiting for the viewer",
        "revive.receiver_dropped_show": "the receiver dropped the show",
        "revive.source_back_waiting": "the source is back - waiting for the stream to be ready",
        "revive.source_unreadable_wait": (
            "the source is unreadable ({why}) - waiting for it to return, "
            "I will bring the show back myself"
        ),
        "revive.pack_broke": "the pack broke off: {trouble}",
        "revive.fully_warm_switch_disk": (
            "fully warmed - stopping the live pack, playing from disk"
        ),
        "revive.tail_ended": (
            "end of the picture: the pointer has stood at {pos} for {secs} s already - "
            "calling it watched"
        ),
        "revive.closed_by_remote": "{tag} show closed from the remote at {pos} - not bringing it back",
        "revive.source_restarted": "TorrServer restarted - returned the pack by magnet",
        "revive.source_back_readded": "the source is back - added the pack by magnet again",
    }
