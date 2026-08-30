"""Английские надписи кластера ранжирования релизов."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера ранжирования."""
    return {
        "rank.lang_japanese": "Japanese",
        "rank.lang_english": "English",
        "rank.lang_korean": "Korean",
        "rank.lang_chinese": "Chinese",
        "rank.lang_french": "French",
        "rank.lang_german": "German",
        "rank.lang_spanish": "Spanish",
        "rank.lang_italian": "Italian",
        "rank.lang_original": "original",
        "rank.stepdown_dead_swarm": "the swarm is dead",
        "rank.stepdown_rejected": "rejected ({why})",
        "rank.stepdown_not_reached": "never got to it",
        "rank.stepdown_no_answer": "did not answer",
        "rank.stepdown_dropped": "never made the queue: {reason}",
        "rank.stepdown_note": (
            "took {took}, next in line was {rival} (release {at}, {seeders} seeders) - {why}"
        ),
        "rank.no_audio_tracks": "the file has no audio tracks",
        "rank.voice_kept_usual": ("no “{name}” voice track in this release - taking the usual one"),
        "rank.voice_number_missing": (
            "tracks: {total}, no number {number} - check: cast voices <query>"
        ),
        "rank.voice_name_missing": (
            "no “{name}” voice track in this release - check: cast voices <query>"
        ),
        "rank.voice_question": "Voice track?",
        "rank.no_language_tag_russian": (
            "sound has no language tag - the release name says Russian"
        ),
        "rank.language_unknown": (
            "track language unknown - the release did not name the voice language"
        ),
        "rank.only_lang_other_release": (
            "{lang} sound only - the catalog may hold a dub in another release"
        ),
        "rank.only_lang_separate_file": (
            "{lang} sound only - the catalog has a dub, but it sits in a separate file"
        ),
        "rank.only_lang_no_dub": "{lang} sound only, no dub in the catalog",
        "rank.voice_original": "the original",
        "rank.voice_russian": "the Russian one",
        "rank.kind_dub": "the dub",
        "rank.kind_multi": "the multi-voice one",
        "rank.kind_dual": "the dual-voice one",
        "rank.kind_mono": "the single-voice one",
        "rank.voice_own_reason": " - the picture was shot in Russian, this is its own track",
        "rank.voice_studio_tier": " - this studio sits at the “{tier}” tier with us",
        "rank.voice_note": "rus tracks: {russian}, taking {what}{tail}{why}",
        "rank.understated_named": "named {named}, actually {actual}",
        "rank.understated_actual_only": "actually {actual}",
        "rank.track_unnamed": "unnamed",
        "rank.size_gb": "{value} GB",
        "rank.default_mark": "default",
        "rank.remembered_mark": "remembered",
        "rank.voices_header": "Voice tracks:",
        "rank.table_quality": "Quality",
        "rank.table_size": "Size",
        "rank.table_seeders": "Seeders",
        "rank.table_voice": "Voice",
        "rank.table_studio": "Studio",
        "rank.table_codec": "Codec",
        "rank.table_header": "Releases:",
        "rank.table_more_hidden": "  ... and {count} more with fewer seeders",
        "rank.table_estimated_note": (
            "  weight marks are estimated by duration: neither the file passport nor "
            "the blurb named it"
        ),
        "rank.reason_off_season": "no matching season",
        "rank.reason_no_episode": "no matching episode by name",
        "rank.reason_disc": "disc image",
        "rank.reason_extras": "extras, not the picture itself",
        "rank.reason_heavy": "heavier than the ceiling",
        "rank.reason_hevc": "hevc, and no full recode",
        "rank.reason_codec": "wrong codec",
        "rank.reason_small": "frame below 720p by name",
        "rank.reason_source": "source is not HD",
        "rank.reason_quiet": "the name says nothing about quality",
        "rank.reason_pinned": "release named by hand",
    }
