"""Зеркало слова о показе: пауза видна стоящей закладкой, собственный ``toggle`` моста
переворачивает слово сразу, а темнота - не «играю»."""

from __future__ import annotations

from hass.motion import IDLE, PAUSED, PLAYING, STARTING, TORN, Motion
from torrcast.domain.playback_snapshot import PlaybackSnapshot


class _Clock:
    """Часы теста: время идёт ровно туда, куда его двигают."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _shown(
    position: float,
    dark: float = 0.0,
    moved: bool = True,
    key: str = "movie:муха",
    paused: str = "",
) -> PlaybackSnapshot:
    return PlaybackSnapshot(
        key=key,
        title="Муха",
        position=position,
        duration=3600.0,
        dark_since=dark,
        moved=moved,
        paused=paused,
    )


def test_a_bookmark_that_keeps_moving_is_never_called_a_pause() -> None:
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(60.0), active=True, starting=False) == PLAYING
    clock.now = 30.0
    assert motion.phase(_shown(90.0), active=True, starting=False) == PLAYING


def test_a_bookmark_standing_longer_than_the_threshold_is_a_pause() -> None:
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0), active=True, starting=False)
    clock.now = 20.0  # сторож показа пишет закладку раз в 10 с: тут ещё не пауза
    assert motion.phase(_shown(60.0), active=True, starting=False) == PLAYING
    clock.now = 26.0
    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED


def test_a_dark_screen_is_not_called_playing_even_with_a_live_unit() -> None:
    motion = Motion(clock=_Clock())

    assert motion.phase(_shown(60.0, dark=1.0), active=True, starting=False) == TORN


def test_a_dark_record_without_a_show_of_its_own_is_not_called_torn() -> None:
    """🔴 TC-1022. Юнита нет - показа нет, и колесу над мёртвой записью крутиться нечего.

    Темнота остаётся в записи и после конца показа нарочно: ею ``cast status``
    рассказывает, чем кончился прошлый сеанс. Но карточка тем же словом рисует «ещё на
    подходе», и подъём, не поднявшийся с первого раза, оставлял её в ``torn`` до
    следующего запуска - при том, что ``cast stop`` на том же мосту отвечал «ничего не
    играет». Одно слово на две стороны: показа нет.
    """
    motion = Motion(clock=_Clock())

    said = motion.phase(_shown(60.0, dark=1.0), active=False, starting=False)

    assert said == IDLE, f"мёртвая запись названа карточке словом «{said}»"


def test_a_bookmark_that_has_not_given_a_frame_yet_is_not_a_pause() -> None:
    """Position stuck at 0 is a show still loading, not a viewer's pause."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(0.0, moved=False), active=True, starting=False)
    clock.now = 30.0
    assert motion.phase(_shown(0.0, moved=False), active=True, starting=False) == PLAYING


def test_a_resumed_bookmark_that_has_not_moved_this_launch_is_not_a_pause() -> None:
    """A resume starts on a positive bookmark from a past session, not this one.

    TC-1002, live acceptance 03-09-2026: a continuation of a show landed on 2335.8 s from
    the previous watch, the receiver never gave a single frame in the new launch, and the
    card still said `paused` after the still threshold - a black screen called a pause.
    A stuck POSITION cannot tell the two apart; only the fact that a frame was produced
    since this launch can, and here it was not.
    """
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(2335.8, moved=False), active=True, starting=False)
    clock.now = 30.0
    assert motion.phase(_shown(2335.8, moved=False), active=True, starting=False) == PLAYING


def test_a_show_that_is_being_started_and_a_silent_machine() -> None:
    motion = Motion(clock=_Clock())

    assert motion.phase(None, active=False, starting=True) == STARTING
    assert motion.phase(None, active=False, starting=False) == IDLE


def test_the_bridges_own_toggle_names_the_pause_at_once() -> None:
    """Пауза с карточки - слово самого моста: ждать стоящей закладки не нужно."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(60.0), active=True, starting=False) == PLAYING
    motion.toggle()

    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED
    clock.now = 5.0
    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED


def test_the_watchers_last_write_after_a_toggle_does_not_lift_the_latch() -> None:
    """Сторож пишет раз в 10 с: после команды на диск может лечь ещё одна запись
    идущего показа - она не «поехала снова», а доехала до места паузы."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0), active=True, starting=False)
    motion.toggle()

    clock.now = 10.0
    assert motion.phase(_shown(68.0), active=True, starting=False) == PAUSED
    clock.now = 20.0
    assert motion.phase(_shown(68.0), active=True, starting=False) == PAUSED


def test_a_toggle_the_show_never_took_is_taken_back_by_a_moving_bookmark() -> None:
    """Защёлку снимает факт, а не таймер: закладка поехала дальше запаса - показ идёт."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0), active=True, starting=False)
    motion.toggle()
    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED

    clock.now = 10.0
    assert motion.phase(_shown(90.0), active=True, starting=False) == PLAYING
    clock.now = 20.0
    assert motion.phase(_shown(120.0), active=True, starting=False) == PLAYING


def test_a_toggle_from_a_measured_pause_names_the_show_playing_at_once() -> None:
    """Снятие паузы с карточки - та же защёлка: «играю» называется в секунду команды.

    Стояние при этом считается заново от команды: старая пауза пульта ТВ, которую
    команда как раз сняла, не должна снимать защёлку «играю» на первом же опросе.
    """
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0), active=True, starting=False)
    clock.now = 26.0
    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED  # пульт ТВ

    motion.toggle()
    assert motion.phase(_shown(60.0), active=True, starting=False) == PLAYING


def test_a_resume_the_show_never_took_falls_back_to_the_measured_pause() -> None:
    """«Играю» из защёлки живёт, пока закладка не простояла порог после команды:
    простояла - приёмник снятие не взял, и слово возвращается к замеру."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0), active=True, starting=False)
    motion.toggle()
    motion.phase(_shown(60.0), active=True, starting=False)
    motion.toggle()
    assert motion.phase(_shown(60.0), active=True, starting=False) == PLAYING

    clock.now = 30.0
    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED


def test_the_latch_does_not_follow_into_the_next_show() -> None:
    """Защёлка ставится на тот показ, что видит замер: другой ключ её не наследует."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0), active=True, starting=False)
    motion.toggle()
    assert motion.phase(_shown(60.0), active=True, starting=False) == PAUSED

    assert motion.phase(_shown(5.0, key="movie:тачки"), active=True, starting=False) == PLAYING


def test_a_toggle_on_a_show_that_gave_no_frame_does_not_fake_a_pause() -> None:
    """Правило TC-1002 стоит и под защёлкой: кадра в этом запуске не было - стоять
    нечему, и слово остаётся у замера, а не у команды."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(2335.8, moved=False), active=True, starting=False) == PLAYING
    motion.toggle()

    assert motion.phase(_shown(2335.8, moved=False), active=True, starting=False) == PLAYING


def test_a_pause_made_by_the_remote_is_named_from_the_fact_on_the_first_poll() -> None:
    """Пульт телевизора: запись уже несёт слово приёмника - ждать порога нечего."""
    motion = Motion(still=25.0, clock=_Clock())

    assert motion.phase(_shown(60.0, paused="PAUSED"), active=True, starting=False) == PAUSED


def test_a_playing_fact_is_named_playing_however_long_the_bookmark_stands() -> None:
    """Факт сильнее замера: стоящая дольше порога закладка паузой не зовётся."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False)
    clock.now = 100.0

    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING


def test_a_remote_resume_after_a_card_pause_is_named_from_the_fact() -> None:
    """Пауза с карточки, снятие пультом: защёлку снимает факт записи, а не запас закладки."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING
    motion.toggle()  # пауза с карточки
    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PAUSED
    clock.now = 2.0
    assert motion.phase(_shown(60.0, paused="PAUSED"), active=True, starting=False) == PAUSED

    clock.now = 900.0
    assert motion.phase(_shown(60.0, paused="PAUSED"), active=True, starting=False) == PAUSED
    # зритель снял паузу пультом - запись это уже назвала
    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING


def test_the_latch_holds_while_the_command_is_landing() -> None:
    """Факт, расходящийся с командой внутри окна приземления, - это ещё СТАРЫЙ факт."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING
    motion.toggle()

    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PAUSED
    clock.now = 5.0
    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PAUSED


def test_a_toggle_the_receiver_never_took_falls_back_to_the_fact() -> None:
    """Окно приземления вышло, а факт прежний - приёмник команду не взял."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING
    motion.toggle()
    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PAUSED

    clock.now = 7.0
    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING


def test_the_resume_latch_holds_against_the_stale_pause_fact() -> None:
    """Снятие с карточки - та же защёлка: запись ещё несёт «паузу», а слово уже «играю»."""
    clock = _Clock()
    motion = Motion(still=25.0, clock=clock)

    assert motion.phase(_shown(60.0, paused="PAUSED"), active=True, starting=False) == PAUSED
    motion.toggle()

    assert motion.phase(_shown(60.0, paused="PAUSED"), active=True, starting=False) == PLAYING
    clock.now = 2.0
    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING


def test_a_pause_fact_without_a_frame_this_launch_is_not_a_pause() -> None:
    """Правило TC-1002 стоит и под фактом: кадра в этом запуске не было - не пауза."""
    motion = Motion(clock=_Clock())

    assert (
        motion.phase(_shown(2335.8, moved=False, paused="PAUSED"), active=True, starting=False)
        == PLAYING
    )


def test_the_latch_does_not_follow_into_the_next_show_under_the_fact() -> None:
    """Другой показ не наследует защёлку, даже внутри окна приземления команды."""
    motion = Motion(clock=_Clock())

    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PLAYING
    motion.toggle()
    assert motion.phase(_shown(60.0, paused="PLAYING"), active=True, starting=False) == PAUSED

    assert (
        motion.phase(_shown(5.0, key="movie:тачки", paused="PLAYING"), active=True, starting=False)
        == PLAYING
    )
