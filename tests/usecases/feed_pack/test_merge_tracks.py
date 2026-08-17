"""Склейка сегмента: картинка перекода, звук копии и поправка на ленту прогона."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import torrcast.usecases.feed_pack._state as _state
from torrcast.usecases.feed_pack.merge_tracks import merge_tracks

if TYPE_CHECKING:
    import pytest


@dataclass
class _Done:
    returncode: int = 0


@dataclass
class _Subprocess:
    """ffmpeg под рукой зеркала: пишет то, что велено, и запоминает команду."""

    code: int = 0
    payload: bytes = b"mixed"
    boom: bool = False
    seen: list[list[str]] = field(default_factory=list)
    SubprocessError: type[Exception] = OSError

    def run(self, command: list[str], **kwargs: Any) -> _Done:
        if self.boom:
            raise OSError("нет ffmpeg")
        self.seen.append(command)
        if self.payload:
            Path(command[-1]).write_bytes(self.payload)
        return _Done(returncode=self.code)


def _ffmpeg(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _Subprocess:
    fake = _Subprocess(**kwargs)
    monkeypatch.setattr(_state, "subprocess", fake)
    return fake


def _pieces(root: Path) -> tuple[Path, Path, Path]:
    video, audio = root / "recode.ts", root / "copy.ts"
    video.write_bytes(b"v")
    audio.write_bytes(b"a")
    return video, audio, root / "mixed.ts"


def test_the_picture_comes_from_the_recode_and_the_sound_from_the_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Звук показа обязан остаться одним потоком одного кодировщика - отсюда порядок дорожек."""
    ffmpeg = _ffmpeg(monkeypatch)
    video, audio, dst = _pieces(tmp_path)

    assert merge_tracks(video, audio, dst) is True
    command = ffmpeg.seen[0]
    assert command[command.index("-map") : command.index("-map") + 4] == [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
    ]
    assert command[command.index("-i") + 1] == str(video)
    assert "-c" in command and command[command.index("-c") + 1] == "copy"


def test_a_meaningful_shift_lands_the_picture_on_the_timeline_of_this_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сдвиг больше полкадра ставится ``-itsoffset``; ниже - сдвига нет, а не крошечный."""
    ffmpeg = _ffmpeg(monkeypatch)
    video, audio, dst = _pieces(tmp_path)

    merge_tracks(video, audio, dst, shift=0.0417)
    assert ffmpeg.seen[-1][ffmpeg.seen[-1].index("-itsoffset") + 1] == "0.041700"

    merge_tracks(video, audio, dst, shift=0.0005)
    assert "-itsoffset" not in ffmpeg.seen[-1]


def test_a_merge_that_did_not_work_never_lies_and_leaves_no_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Не вышло - ``False`` и никакого огрызка: иначе выкладка отдала бы его наружу."""
    _ffmpeg(monkeypatch, code=1)
    video, audio, dst = _pieces(tmp_path)
    assert merge_tracks(video, audio, dst) is False and not dst.exists()

    _ffmpeg(monkeypatch, payload=b"")
    assert merge_tracks(video, audio, dst) is False and not dst.exists()

    _ffmpeg(monkeypatch, boom=True)
    assert merge_tracks(video, audio, dst) is False and not dst.exists()


def test_an_empty_result_is_not_a_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Нулевой файл - это не склейка: приёмник получил бы пустое место вместо куска."""
    _ffmpeg(monkeypatch, payload=b"\x00" * 0)
    video, audio, dst = _pieces(tmp_path)
    dst.write_bytes(b"")

    assert merge_tracks(video, audio, dst) is False
