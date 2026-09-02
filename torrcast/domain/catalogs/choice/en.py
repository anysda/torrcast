"""Английские надписи кластера выбора картины."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера выбора.

    Английский - и умолчание продукта, и запасной каталог: ключа, которого тут нет,
    не существует вовсе, и :func:`torrcast.domain.catalogs.phrase.phrase` на нём падает
    громко, а не отвечает пустотой.
    """
    return {
        "choice.quoted": "“{it}”",
        "choice.series_mark": ", series",
        "choice.no_part_mark": ", no part number",
        "choice.russian_title_only": " - Russian title only",
        "choice.remote_command": "remote: {command}",
        "choice.pick_out_of_range": "matching pictures: {total}, no number {pick} there",
        "choice.pick_moved": (
            "number {pick} in the “{asked}” table stood for “{was}”, and now it stands "
            "for “{now}” - that is a different picture; fresh numbers: cast releases "
            "{asked}"
        ),
        "choice.playing_pick": "playing “{picture}” - item {pick}, named by --pick",
        "choice.single_no_menu": "matching pictures: 1 - “{picture}”, no menu needed",
        "choice.blind_refusal": (
            "matching pictures: {total}, and there is no terminal - I do not choose "
            "blindly; name the picture exactly (“{example}”, for one) or its number "
            "(--pick N), or run cast in a terminal"
        ),
        "choice.question": "What are we watching?",
        "choice.absent_part": (
            "“{name}”: part one is not in the results; taking the first live one found "
            "- “{picture}”; {total} pictures matched in all; the rest: cast {asked} "
            "--menu"
        ),
        "choice.default": "Enter - “{picture}”, item {number} of {total}",
        "choice.note_instead": "taking “{mine}”, not “{other}”",
        "choice.note_instead_asked": "you asked for “{asked}” - taking “{mine}”, not “{other}”",
        "choice.note_instead_why": "taking “{mine}”, not “{other}”: {why}",
        "choice.note_instead_asked_why": (
            "you asked for “{asked}” - taking “{mine}”, not “{other}”: {why}"
        ),
        "choice.note_namesake": (
            "taking “{mine}”: {others} go under that name too - a different picture"
        ),
        "choice.note_namesake_asked": (
            "you asked for “{asked}” - taking “{mine}”: {others} go under that name too "
            "- a different picture"
        ),
        "choice.note_season": (
            "taking “{mine}”: season {season} was asked for, and the results hold none "
            "of it - this one is part {part}"
        ),
        "choice.note_season_asked": (
            "you asked for “{asked}” - taking “{mine}”: season {season} was asked for, "
            "and the results hold none of it - this one is part {part}"
        ),
        "choice.why_other_kind": "a series was asked for, and this is another kind",
        "choice.why_nothing_playable": "nothing to play there - not one sound release",
        "choice.why_dead_swarm": "its swarm is dead - {seeds} seeds",
        "choice.why_no_hd": "no live HD there - old stuff only",
        "choice.why_single_release": "it has a single release, and this one has {taken}",
        "choice.last_hope_episode": (
            "no live non-HEVC release of episode {want} - taking HEVC as the last hope"
        ),
        "choice.last_hope_picture": (
            "no live non-HEVC release of the picture - taking HEVC as the last hope"
        ),
        "choice.lone_other_part": (
            "“{name}”: part one is not in the results, and another part I do not start "
            "on my own - there is “{picture}”, ask for it by number: “{name} {part}”"
        ),
        "choice.lone_other_part_taken": (
            "“{name}”: part one is not in the results - taking the first live one, "
            "“{picture}”, part {part}; another one: cast {name} --menu"
        ),
        "choice.guard_taken": (
            "{guard}; taking the first live one, “{taken}”; another one: cast {asked} --menu"
        ),
        "choice.default_taken": (
            "taking the first live one, “{picture}” - {total} pictures matched; another "
            "one: cast {asked} --menu"
        ),
        "choice.series_taken": (
            "taking “{picture}” - this name has both a film and a series, and the series "
            "I take on my own; the film “{other}”: cast {asked} --menu"
        ),
        "choice.named_unplayable": (
            "“{name}” is {whom}; it does not play: {why}; another picture (“{taken}”) I "
            "do not start instead on my own - here is what there is, name the number"
        ),
        "choice.named_not_default": (
            "“{name}” is {whom}, and another picture - “{taken}” - stands as the default "
            "(first live one by chronology); which of them to watch I do not decide on "
            "my own - here is what there is, name the number"
        ),
        "choice.named_taken_alive": (
            "“{name}” is {whom}; taking the liveliest of them - “{took}”; {total} "
            "pictures matched in all; another one: cast {asked} --menu"
        ),
        "choice.named_taken_unplayable": (
            "“{name}” is {whom}, and it does not play: {why}; taking the liveliest - "
            "“{took}”; {total} pictures matched in all; another one: cast {asked} --menu"
        ),
        "choice.namesake_taken": (
            "taking “{picture}” - the liveliest of the namesakes, its best release has "
            "{seeds} seeds; other pictures under that name: {others}, their list: cast "
            "{asked} --menu"
        ),
        "choice.namesake_two": (
            "“{title}” ({year}): two pictures share that name and year - the reference "
            "knows “{other}” as well, and there is nothing to tell them apart by name "
            "and year"
        ),
        "choice.part_one_absent": (
            "“{name}”: part one is not in the results, and another part I do not start "
            "instead on my own - here is what there is, name the number"
        ),
        "choice.part_one_dead": (
            "“{picture}” does not play; another part I do not start instead on my own - "
            "here is what there is, name the number"
        ),
        "choice.part_one_dead_why": (
            "“{picture}” does not play: {why}; another part I do not start instead on "
            "my own - here is what there is, name the number"
        ),
        "choice.taken": (
            "taking “{picture}” - {total} pictures matched; another one: cast releases "
            "{asked} and --pick N"
        ),
        "choice.understudy": (
            "“{failed}” - nothing to play it with ({why}); moving to “{spare}”: {releases} releases"
        ),
        "choice.mark_recode_all": "recoding whole",
        "choice.mark_not_taken": "not taken",
        "choice.mark_heavy": "heavy",
        "choice.mark_recode_parts": "recoding parts",
        "choice.year_note": (
            "taking “{title}” of {year}, and the reference knows this picture as {known}"
        ),
        "choice.year_note_asked": (
            "you asked for “{asked}” - taking “{title}” of {year}, and the reference "
            "knows this picture as {known}"
        ),
    }
