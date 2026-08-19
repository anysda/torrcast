"""Зеркало :mod:`torrcast.usecases.select_bench._bench_tally`: счёт обхода очереди."""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.release import Release
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench_tally import _Tally


def _rel(name: str = "Кино 1080p") -> Release:
    return Release(raw_name=name, title="Кино")


def _judged(number: int, media: Media) -> _Prep:
    """Раздача, которую ffprobe прочитал и осудил: приговор, а не молчание роя."""
    prep = _Prep(number=number, release=_rel(), started=0.0)
    prep.media = media
    return prep


def _silent(number: int) -> _Prep:
    """Раздача, промолчавшая роем: про качество релиза не узнали ничего."""
    prep = _Prep(number=number, release=_rel(), started=0.0)
    prep.error = "нет пиров"
    return prep


def test_a_silent_swarm_costs_no_verdict_and_no_seconds() -> None:
    """Молчание роя и приговор ffprobe считаются врозь: терпение жжёт только приговор."""
    tally = _Tally()

    tally.note(1, _silent(1), "нет пиров", since=0.0, clock=lambda: 30.0)

    assert (tally.verdicts, tally.silents, tally.priced) == (0, 1, 0.0)
    assert tally.tried == ["1 - нет пиров"]


def test_a_verdict_is_priced_by_the_seconds_the_person_waited_for_it() -> None:
    """Приговор стоит человеку ровно ожидания: дешёвый не отнимает места у следующего."""
    tally = _Tally()

    tally.note(2, _judged(2, Media(video="av1")), "кодек av1", since=10.0, clock=lambda: 12.0)

    assert (tally.verdicts, tally.silents, tally.priced) == (1, 0, 2.0)
    assert tally.judged == {2: "кодек av1"}


def test_the_spare_kept_is_the_one_less_is_known_bad_about() -> None:
    """Незнание вытесняет знание «нет»: безымянная дорожка ещё может оказаться русской."""
    forgotten: list[int] = []
    named_foreign = _judged(1, Media(tracks=(AudioTrack(index=0, language="jpn"),)))
    unnamed = _judged(2, Media(tracks=(AudioTrack(index=0),)))
    tally = _Tally()

    tally.hold(named_foreign, voiceless=True, forget=lambda prep: forgotten.append(prep.number))
    assert tally.mute is named_foreign

    tally.hold(unnamed, voiceless=True, forget=lambda prep: forgotten.append(prep.number))
    assert tally.mute is unnamed, "знание «нет» вытеснило незнание"
    assert forgotten == [1], "прежний запасной остался греться впустую"


def test_a_release_that_has_a_voice_is_let_go_rather_than_kept_as_a_spare() -> None:
    """Запасной ход держит только безрусских: годного по звуку тут держать нечего."""
    forgotten: list[int] = []
    tally = _Tally()

    tally.hold(
        _judged(3, Media()), voiceless=False, forget=lambda prep: forgotten.append(prep.number)
    )

    assert (tally.mute, forgotten) == (None, [3])
