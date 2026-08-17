"""Сдвиг лент копии и перекода: мерится по первым пакетам, а не предполагается нулём."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import torrcast.usecases.feed_pack._state as _state
from torrcast.usecases.feed_pack.timeline_shift import timeline_shift

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@dataclass
class _Done:
    stdout: bytes


@dataclass
class _Subprocess:
    """ffprobe под рукой зеркала: отвечает заготовленным, а не читает файлы."""

    answers: list[Any]
    seen: list[list[str]] = field(default_factory=list)
    SubprocessError: type[Exception] = OSError

    def run(self, command: list[str], **kwargs: Any) -> _Done:
        self.seen.append(command)
        answer = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return _Done(stdout=answer.encode("utf-8"))


def _probe(monkeypatch: pytest.MonkeyPatch, *answers: Any) -> _Subprocess:
    fake = _Subprocess(answers=list(answers))
    monkeypatch.setattr(_state, "subprocess", fake)
    return fake


def test_the_shift_is_the_difference_of_the_first_packets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """У обоих кусков первый пакет - один и тот же опорный кадр: разница меток и есть сдвиг."""
    probe = _probe(monkeypatch, "10.100,\n10.140,\n", "10.058,\n10.100,\n")

    assert timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts") == 10.100 - 10.058
    assert len(probe.seen) == 2 and "ffprobe" in probe.seen[0]


def test_a_difference_over_a_second_means_we_measured_the_wrong_thing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Секунда между кусками ОДНОГО места невозможна: такой ответ - не сдвиг, а ошибка."""
    _probe(monkeypatch, "10.0,\n", "8.0,\n")

    assert timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts") is None


def test_an_unreadable_piece_is_answered_by_an_honest_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Нет ffprobe или битый кусок - врать нулём нельзя: ответ «не сверили»."""
    _probe(monkeypatch, OSError("нет ffprobe"))
    assert timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts") is None

    _probe(monkeypatch, "мусор без чисел\n")
    assert timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts") is None


def test_the_earliest_packet_of_each_piece_is_the_one_that_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Метки приходят не по порядку (B-кадры): берётся самая ранняя, а не первая строка."""
    _probe(monkeypatch, "10.3,\n10.1,\n10.2,\n", "10.0,\n10.4,\n")

    assert round(timeline_shift(tmp_path / "c.ts", tmp_path / "r.ts") or -1.0, 3) == 0.1
