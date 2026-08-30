"""Русские надписи кластера отбора."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера отбора."""
    return {
        "select.phase_queue": "очередь",
        "select.phase_release": "раздача",
        "select.phase_tracks": "дорожки",
        "select.no_file_chosen": "файл раздачи не выбран",
        "select.stream_not_read": "поток не прочитан",
        "select.timing": "метаданные {meta} с, дорожки {read} с",
        "select.replay_from_start": (
            "«{title}» - {label} была последней в раздаче, поэтому играю с начала"
        ),
        "select.buried_place": " с {pos}",
        "select.buried_note": (
            "«{title}»{named} - записанная раздача не играется: {why}; ищу другую{place}"
        ),
        "select.file_gone": "файла №{index} в ней больше нет",
        "select.timed_out": "не дождались за {secs} с",
        "select.gave_up": "не дождались",
        "select.release_missing_new_listing": (
            "показанного релиза {release} у «{title}» в новой выдаче нет"
        ),
        "select.release_number_missing": "у «{title}» релизов {total}, номера {release} нет",
        "select.other_menu": "выбрать другое: --menu",
        "select.track_number": "дорожка {number}",
        "select.from_position": "с {pos}",
    }
