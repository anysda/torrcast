"""Английские надписи кластера показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера показа.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "playback.session_tag": "[session {id}]",
        "playback.dry_run_no_cast": "(--dry) {about} - not casting",
        "playback.now_playing": "playing {about} - on TV   (start {secs:.0f} s)",
        "playback.now_playing_tagged": "{tag} playing {about} - on TV   (start {secs:.0f} s)",
        "playback.frame_too_big": (
            "{quality} - the receiver only takes this frame size recoded, and recoding "
            "is off: needs a release at {limit}p or below"
        ),
        "playback.waiting_tv": "waiting for the TV",
        "playback.packing": "packing",
        "playback.did_not_start": "the show did not start: {why}",
        "playback.picture_undetected_but_playing": (
            "could not prove a picture within {secs:.0f} s, but the show is playing: {said}"
        ),
        "playback.did_not_start_timeout": "the show did not start within {secs:.0f} s - {said}",
        "playback.raising_myself": "{tag} {why} - raising the show myself",
        "playback.watched_cleared_warm": "watched to the end - cleared the warmed copy from disk",
        "playback.no_picture_source_unreadable": (
            "not a single picture was shown: the source is unreadable ({why})"
        ),
        "playback.source_unreadable_cut_short": (
            "the source is unreadable ({why}) - the show was cut short, numbers above"
        ),
        "playback.no_picture_receiver_refused": (
            "not a single picture was shown: the receiver would not take the show - "
            "could not bring it back"
        ),
        "playback.receiver_did_not_finish": (
            "the receiver did not finish the stream - numbers above"
        ),
        "playback.file_number_missing": (
            "there are {total} video files in this release, no number {number} there"
        ),
        "playback.picking_largest_file": (
            "there are {total} video files in this release - playing the largest, "
            "its share {share:.2f}"
        ),
        "recoder.profile_container": "weight profile: container {mbit:.1f} Mbit/s, ",
        "recoder.basis_estimate": "an estimate",
        "recoder.basis_measurement": "a measurement",
        "recoder.tv_weight": "will reach the TV at {mbit:.1f} Mbit/s, by {basis}",
        "recoder.no_track_weight": (
            "no video track weight in the passport - I will learn the correction as I go"
        ),
        "recoder.map_not_grid": " (the map is not a grid, but its weight is honest)",
        "recoder.flat_profile": (
            "flat weight profile: {mbit:.1f} Mbit/s per piece, by {basis} - I do not know "
            "the heavy spot by sight, shrinking by the average"
        ),
        "recoder.no_profile": (
            "no weight profile: neither a map nor a track weight in the passport - "
            "shrinking the heavy piece as it comes up in the pack"
        ),
        "recoder.map_no_offsets": "the map has no offsets - cannot build piece weights from it",
        "playback.tonemap_no_headroom": (
            "⚠️ 4K tonemap is on: it eats the recode speed headroom - packing "
            "keeps pace with the show, no room left against stalls"
        ),
    }
