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


def test_the_spare_kept_is_the_one_whose_language_is_named() -> None:
    """🔴 TC-741. Отложенным становится только тот, чей язык паспорт назвал вслух.

    Про безымянную дорожку сказать зрителю нечего: «русской не нашли» от «нашли, но не
    назвали» её не отличить. Прежде она вытесняла названного соперника и играла запасным
    ходом - то есть отбор возвращался к релизу, который сам же забраковал.
    """
    forgotten: list[int] = []
    named_foreign = _judged(1, Media(tracks=(AudioTrack(index=0, language="jpn"),)))
    unnamed = _judged(2, Media(tracks=(AudioTrack(index=0),)))
    tally = _Tally()

    tally.hold(named_foreign, voiceless=True, forget=lambda prep: forgotten.append(prep.number))
    assert tally.mute is named_foreign

    tally.hold(unnamed, voiceless=True, forget=lambda prep: forgotten.append(prep.number))
    assert tally.mute is named_foreign, "незнание запасным ходом не становится"
    assert forgotten == [2], "безымянный отпущен, а не оставлен греться"
    assert tally.voiceless == 2, "звуком забракованы оба - это и есть причина отказа"


def test_a_release_that_has_a_voice_is_let_go_rather_than_kept_as_a_spare() -> None:
    """Запасной ход держит только безрусских: годного по звуку тут держать нечего."""
    forgotten: list[int] = []
    tally = _Tally()

    tally.hold(
        _judged(3, Media()), voiceless=False, forget=lambda prep: forgotten.append(prep.number)
    )

    assert (tally.mute, forgotten) == (None, [3])


def test_the_patience_shrinks_to_the_voice_budget_once_a_spare_is_in_hand() -> None:
    """🔴 TC-968. Пока показывать нечего - ждём как ждали; отложили запасного - терпение своё.

    Мера тут секунды, а не попытки: одна молчащая раздача стоит трёх ответивших, и на стенде
    ровно она и держала показ. Остаток бюджета убывает на то, что обход уже потратил.
    """
    tally = _Tally(voice_budget=4.0)
    assert tally.patience(deadline=100.0, entered=10.0) == 100.0, "запасного нет - потолка нет"

    tally.mute = _judged(1, Media(tracks=(AudioTrack(index=0, language="jpn"),)))
    assert tally.patience(deadline=100.0, entered=10.0) == 14.0

    tally.hunted = 2.5
    assert tally.patience(deadline=100.0, entered=20.0) == 21.5, "остаток бюджета, а не бюджет"

    tally.hunted = 0.0
    assert tally.patience(deadline=12.0, entered=10.0) == 12.0, "потолок фазы ниже - он и главный"

    tally.hunted = 9.0
    assert tally.patience(deadline=100.0, entered=30.0) == 30.0, "перебрал - ждать нечего"
