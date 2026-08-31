"""Английские надписи кластера стенда отбора."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера стенда отбора."""
    return {
        "select_bench.phase_metadata_dht": "metadata (DHT)",
        "select_bench.phase_done": "done",
        "select_bench.phase_failed": "failure",
        "select_bench.phase_missed_budget": "phase “{phase}” missed its budget",
        "select_bench.voice_search_phase": (
            "looking for an English voice: release {number} of {total} - "
        ),
        "select_bench.honest_phase": "release {chosen} {look} - checking {number}",
        "select_bench.reason_no_answer": "did not answer in time",
        "select_bench.honest_no_answer_note": (
            "release {number} did not answer in time - playing {chosen} ({look})"
        ),
        "select_bench.unfit_note": "release {number} does not fit ({why})",
        "select_bench.reason_no_voice": "no English voice",
        "select_bench.honest_no_voice_note": "release {number} is not better (no English voice)",
        "select_bench.reason_not_better": "not better ({quality})",
        "select_bench.honest_not_better_note": "release {number} is not better ({quality})",
        "select_bench.honest_taken_note": (
            "release {chosen} {short} - taking {number} (actually {quality})"
        ),
        "select_bench.honest_kept_note": (
            "release {chosen} {short} - nothing more honest nearby, playing it"
        ),
        "select_bench.reason_thin_swarm": (
            "swarm delivers {got} of the needed {need} Mbit/s ({ratio}x)"
        ),
        "select_bench.tail_take": " - taking {following}",
        "select_bench.voiceless_head": "release {number} has no English voice ({lang})",
        "select_bench.no_swarm_capacity": (
            "no checked swarm can keep up - taking the best, release {number} ({ratio}x)"
        ),
        "select_bench.too_heavy_for_receiver": "too heavy for the receiver",
        "select_bench.recode_beyond_machine": "recoding this frame is beyond this machine",
        "select_bench.heavy_reason": "{reason}, ~{peak} Mbit/s",
        "select_bench.frame_needs_recode": (
            "{quality} - this frame reaches the receiver only through recoding"
        ),
        "select_bench.mute_fallback_note": (
            "no English voice in any of the checked releases ({tried}) - "
            "turning on release {number}, sound {lang}"
        ),
        "select_bench.skipped_note": (
            "season {want} is missing from releases: {count} (“{name}”...) - "
            "taking the one that has it"
        ),
        "select_bench.supply_note": (
            "release {number}'s swarm delivers {got} at the needed {need} Mbit/s - "
            "taking it ({ratio}x)"
        ),
        "select_bench.recheck_note": (
            "the whole queue stayed silent ({total}) - asking release {number} once more, "
            "alone and without grace periods (waiting up to {budget}s)"
        ),
        "select_bench.recheck_result_alone_silent": "still silent alone",
        "select_bench.recheck_result_alone_unfit": "answered alone, but does not fit",
        "select_bench.recheck_result_note": "release {number} {result} ({trouble})",
        "select_bench.recheck_no_voice_note": (
            "release {number} answered alone, but without an English voice"
        ),
        "select_bench.refusal_none_fit": "no fit release ({shown}{more})",
        "select_bench.refusal_no_voice": (
            "no English voice in any of the checked releases ({count})"
        ),
        "select_bench.more_tried": " and {count} more",
        "select_bench.refusal_rename_hint": (
            "{refused}: name the picture differently - a different query gathers a different "
            "listing"
        ),
        "select_bench.refusal_move_note": (
            "{refused}: {move} - cast releases <query>, then cast <query> --release N"
        ),
    }
