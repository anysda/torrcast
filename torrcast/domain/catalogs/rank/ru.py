"""Русские надписи кластера ранжирования релизов."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ранжирования."""
    return {
        "rank.lang_japanese": "японский",
        "rank.lang_english": "английский",
        "rank.lang_korean": "корейский",
        "rank.lang_chinese": "китайский",
        "rank.lang_french": "французский",
        "rank.lang_german": "немецкий",
        "rank.lang_spanish": "испанский",
        "rank.lang_italian": "итальянский",
        "rank.lang_russian": "русский",
        "rank.lang_original": "оригинальный",
        "rank.stepdown_dead_swarm": "рой мёртв",
        "rank.stepdown_rejected": "отбраковали ({why})",
        "rank.stepdown_not_reached": "не дошли",
        "rank.stepdown_no_answer": "не ответил",
        "rank.stepdown_dropped": "в очередь не попал: {reason}",
        "rank.stepdown_note": (
            "взял {took}, рядом был {rival} (релиз {at}, сидов {seeders}) - {why}"
        ),
        "rank.no_audio_tracks": "в файле нет звуковых дорожек",
        "rank.voice_kept_usual": "озвучки «{name}» в этом релизе нет - беру обычную",
        "rank.voice_number_missing": (
            "дорожек {total}, номера {number} нет - посмотри: cast voices <запрос>"
        ),
        "rank.voice_name_missing": (
            "озвучки «{name}» в этом релизе нет - посмотри: cast voices <запрос>"
        ),
        "rank.voice_question": "Озвучка?",
        "rank.no_language_tag_dub_by_name": "звук без метки языка - по имени релиза русская",
        "rank.language_unknown": "язык дорожки неизвестен - раздача не назвала язык озвучки",
        "rank.only_lang_other_release": (
            "только {lang} звук - в каталоге, возможно, есть перевод в другой раздаче"
        ),
        "rank.only_lang_separate_file": (
            "только {lang} звук - в каталоге перевод есть, но лежит отдельным файлом"
        ),
        "rank.only_lang_no_dub": "только {lang} звук, перевода в каталоге нет",
        "rank.voice_original": "оригинальную",
        "rank.voice_ours": "русскую",
        "rank.voice_tag": "rus",
        "rank.kind_dub": "дубляж",
        "rank.kind_multi": "многоголосый",
        "rank.kind_dual": "двухголосый",
        "rank.kind_mono": "одноголосый",
        "rank.voice_own_reason": " - картина снята по-русски, это её собственная дорожка",
        "rank.voice_studio_tier": " - эта студия у нас на уровне «{tier}»",
        "rank.voice_note": "дорожек {tag} {count}, беру {what}{tail}{why}",
        "rank.understated_named": "назван {named}, на деле {actual}",
        "rank.understated_actual_only": "на деле {actual}",
        "rank.track_unnamed": "не назван",
        "rank.size_gb": "{value} ГБ",
        "rank.default_mark": "дефолт",
        "rank.remembered_mark": "запомнено",
        "rank.voices_header": "Озвучка:",
        "rank.table_quality": "Качество",
        "rank.table_size": "Размер",
        "rank.table_seeders": "Сиды",
        "rank.table_voice": "Озвучка",
        "rank.table_studio": "Студия",
        "rank.table_codec": "Кодек",
        "rank.table_header": "Релизы:",
        "rank.table_more_hidden": "  ... и ещё {count} с меньшим числом сидов",
        "rank.table_estimated_note": (
            "  пометки веса - по оценке длительности: её не назвали ни паспорт файла, ни справка"
        ),
        "rank.reason_off_season": "нужного сезона нет",
        "rank.reason_no_episode": "нужной серии нет по имени",
        "rank.reason_disc": "образ диска",
        "rank.reason_extras": "дополнительные материалы, а не сама картина",
        "rank.reason_heavy": "тяжелее потолка",
        "rank.reason_hevc": "hevc, а сплошного перекода нет",
        "rank.reason_codec": "кодек не тот",
        "rank.reason_small": "кадр ниже 720p по имени",
        "rank.reason_source": "источник не HD",
        "rank.reason_quiet": "имя молчит о качестве",
        "rank.reason_pinned": "релиз назван руками",
    }
