"""Сдвиг лент копии и перекода: мерится по первым пакетам, а не предполагается нулём."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from torrcast.adapters.stream_pack.timeline_shift import timeline_shift

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Done:
    stdout: bytes


@dataclass
class _Ffprobe:
    """ffprobe под рукой зеркала: отвечает заготовленным, а не читает файлы."""

    answers: list[Any]
    seen: list[list[str]] = field(default_factory=list)

    def run(self, command: list[str], **kwargs: Any) -> _Done:
        self.seen.append(command)
        answer = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return _Done(stdout=answer.encode("utf-8"))


def _probe(*answers: Any) -> _Ffprobe:
    return _Ffprobe(answers=list(answers))


def test_the_shift_is_the_difference_of_the_first_packets(tmp_path: Path) -> None:
    """У обоих кусков первый пакет - один и тот же опорный кадр: разница меток и есть сдвиг."""
    probe = _probe("10.100,\n10.140,\n", "10.058,\n10.100,\n")

    shift = timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts", run=probe.run)
    assert shift == 10.100 - 10.058
    assert len(probe.seen) == 2 and "ffprobe" in probe.seen[0]


def test_a_difference_over_a_second_means_we_measured_the_wrong_thing(tmp_path: Path) -> None:
    """Секунда между кусками ОДНОГО места невозможна: такой ответ - не сдвиг, а ошибка."""
    probe = _probe("10.0,\n", "8.0,\n")

    assert timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts", run=probe.run) is None


def test_an_unreadable_piece_is_answered_by_an_honest_unknown(tmp_path: Path) -> None:
    """Нет ffprobe или битый кусок - врать нулём нельзя: ответ «не сверили»."""
    dead = _probe(OSError("нет ffprobe"))
    assert timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts", run=dead.run) is None

    junk = _probe("мусор без чисел\n")
    assert timeline_shift(tmp_path / "copy.ts", tmp_path / "recode.ts", run=junk.run) is None


def test_the_earliest_packet_of_each_piece_is_the_one_that_counts(tmp_path: Path) -> None:
    """Метки приходят не по порядку (B-кадры): берётся самая ранняя, а не первая строка."""
    probe = _probe("10.3,\n10.1,\n10.2,\n", "10.0,\n10.4,\n")

    shift = timeline_shift(tmp_path / "c.ts", tmp_path / "r.ts", run=probe.run)
    assert round(shift or -1.0, 3) == 0.1


def test_the_shift_of_garbage_is_an_honest_unknown_on_a_live_ffprobe(tmp_path: Path) -> None:
    """Сверить ленту не по чему - так и говорим: ``None``, а не «сдвига нет».

    Тут ffprobe настоящий: заготовленный ответ доказал бы разбор, а не то, что живой
    ffprobe на мусоре и правда не даёт ни одной метки.
    """
    copy, recode = tmp_path / "c.ts", tmp_path / "r.ts"
    copy.write_bytes(b"not a stream")
    recode.write_bytes(b"also not a stream")

    assert timeline_shift(copy, recode) is None
