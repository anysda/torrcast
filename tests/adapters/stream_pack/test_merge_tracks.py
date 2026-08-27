"""Склейка сегмента: картинка перекода, звук копии и поправка на ленту прогона."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from torrcast.adapters.stream_pack.merge_tracks import merge_tracks
from torrcast.domain.segment_container import FMP4


@dataclass
class _Done:
    returncode: int = 0


@dataclass
class _Ffmpeg:
    """ffmpeg под рукой зеркала: пишет то, что велено, и запоминает команду."""

    code: int = 0
    payload: bytes = b"mixed"
    boom: bool = False
    seen: list[list[str]] = field(default_factory=list)

    def run(self, command: list[str], **kwargs: Any) -> _Done:
        if self.boom:
            raise OSError("нет ffmpeg")
        self.seen.append(command)
        if self.payload:
            Path(command[-1]).write_bytes(self.payload)
        return _Done(returncode=self.code)


def _pieces(root: Path) -> tuple[Path, Path, Path]:
    video, audio = root / "recode.ts", root / "copy.ts"
    video.write_bytes(b"v")
    audio.write_bytes(b"a")
    return video, audio, root / "mixed.ts"


def _show_head(scale: int) -> bytes:
    """Заголовок показа: по нему склейка узнаёт, какой шкалой написана его картинка."""

    def box(kind: bytes, payload: bytes = b"") -> bytes:
        return struct.pack(">I", 8 + len(payload)) + kind + payload

    trak = box(
        b"trak",
        box(b"tkhd", b"\x00" * 12 + struct.pack(">I", 1))
        + box(
            b"mdia",
            box(b"mdhd", b"\x00" * 12 + struct.pack(">I", scale))
            + box(b"hdlr", b"\x00" * 8 + b"vide"),
        ),
    )
    return box(b"ftyp", b"iso6") + box(b"moov", trak)


def test_the_picture_comes_from_the_recode_and_the_sound_from_the_copy(tmp_path: Path) -> None:
    """Звук показа обязан остаться одним потоком одного кодировщика - отсюда порядок дорожек."""
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)

    assert merge_tracks(video, audio, dst, run=ffmpeg.run) is True
    command = ffmpeg.seen[0]
    assert command[command.index("-map") : command.index("-map") + 4] == [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
    ]
    assert command[command.index("-i") + 1] == str(video)
    assert "-c" in command and command[command.index("-c") + 1] == "copy"


def test_a_meaningful_shift_lands_the_picture_on_the_timeline_of_this_run(tmp_path: Path) -> None:
    """Сдвиг больше полкадра ставится ``-itsoffset``; ниже - сдвига нет, а не крошечный."""
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)

    merge_tracks(video, audio, dst, shift=0.0417, run=ffmpeg.run)
    assert ffmpeg.seen[-1][ffmpeg.seen[-1].index("-itsoffset") + 1] == "0.041700"

    merge_tracks(video, audio, dst, shift=0.0005, run=ffmpeg.run)
    assert "-itsoffset" not in ffmpeg.seen[-1]


def test_a_merge_that_did_not_work_never_lies_and_leaves_no_stub(tmp_path: Path) -> None:
    """Не вышло - ``False`` и никакого огрызка: иначе выкладка отдала бы его наружу."""
    video, audio, dst = _pieces(tmp_path)
    assert merge_tracks(video, audio, dst, run=_Ffmpeg(code=1).run) is False and not dst.exists()
    assert merge_tracks(video, audio, dst, run=_Ffmpeg(payload=b"").run) is False
    assert not dst.exists()
    assert merge_tracks(video, audio, dst, run=_Ffmpeg(boom=True).run) is False
    assert not dst.exists()


def test_an_empty_result_is_not_a_success(tmp_path: Path) -> None:
    """Нулевой файл - это не склейка: приёмник получил бы пустое место вместо куска."""
    video, audio, dst = _pieces(tmp_path)
    dst.write_bytes(b"")

    assert merge_tracks(video, audio, dst, run=_Ffmpeg(payload=b"").run) is False


def test_a_merge_of_garbage_leaves_no_file_and_says_so_on_a_live_ffmpeg(tmp_path: Path) -> None:
    """Не вышло - значит не вышло: ни файла-огрызка, ни ``True``.

    Тут ffmpeg настоящий: поддельный доказал бы разбор его кода возврата, а не то, что
    живой ffmpeg на мусоре и правда не оставляет склейки.
    """
    video, audio, dst = tmp_path / "v.ts", tmp_path / "a.ts", tmp_path / "mix.ts"
    video.write_bytes(b"not a stream")
    audio.write_bytes(b"also not a stream")

    assert merge_tracks(video, audio, dst) is False
    assert not dst.exists()


def test_the_merge_is_assembled_by_the_muxer_of_the_container_of_the_show(
    tmp_path: Path,
) -> None:
    """Склейка уходит наружу под именем куска, и муксер у неё обязан быть соседский.

    Один ``mpegts`` на оба контейнера значил, что на fMP4 приёмник получал бы под
    расширением ``.m4s`` файл MPEG-TS.
    """
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)

    merge_tracks(video, audio, dst, container=FMP4, run=ffmpeg.run)
    command = ffmpeg.seen[-1]
    assert command[command.index("-f") + 1] == "mp4"
    assert "cmaf" in command[command.index("-movflags") + 1]
    assert "-muxdelay" not in command, "нули меток - лекарство mpegts, и только его"

    merge_tracks(video, audio, dst, run=ffmpeg.run)
    command = ffmpeg.seen[-1]
    assert command[command.index("-f") + 1] == "mpegts" and "-movflags" not in command


def test_a_cmaf_chunk_is_opened_together_with_the_head_of_its_own_run(tmp_path: Path) -> None:
    """🔴 Голый ``moof mdat`` не открыть ничем: на вход идёт кусок ВМЕСТЕ со своим заголовком."""
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)
    picture, sound = tmp_path / "headv.mp4", tmp_path / "heada.mp4"
    picture.write_bytes(b"P")
    sound.write_bytes(b"S")

    assert merge_tracks(video, audio, dst, container=FMP4, heads=(picture, sound), run=ffmpeg.run)
    command = ffmpeg.seen[0]
    fed = [command[i + 1] for i, word in enumerate(command) if word == "-i"]
    assert fed == [f"concat:{picture}|{video}", f"concat:{sound}|{audio}"]


def test_a_head_that_is_not_there_does_not_turn_into_a_guess(tmp_path: Path) -> None:
    """Заголовка нет - кусок идёт на вход как есть: угадывать за выкладку тут нечем."""
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)

    missing = tmp_path / "нет.mp4"
    assert merge_tracks(video, audio, dst, container=FMP4, heads=(missing, None), run=ffmpeg.run)
    command = ffmpeg.seen[0]
    fed = [command[i + 1] for i, word in enumerate(command) if word == "-i"]
    assert fed == [str(video), str(audio)]


def test_the_splice_keeps_the_head_the_muxer_gave_it(tmp_path: Path) -> None:
    """Заголовок с готовой склейки здесь не снимается: голый кусок не читают и наши приборы."""
    ffmpeg = _Ffmpeg(payload=b"\x00\x00\x00\x1cftyp" + b"x" * 20 + b"\x00\x00\x00\x08moof")
    video, audio, dst = _pieces(tmp_path)

    assert merge_tracks(video, audio, dst, container=FMP4, run=ffmpeg.run) is True
    assert dst.read_bytes().startswith(b"\x00\x00\x00\x1cftyp")


def test_the_splice_is_written_in_the_scale_of_the_show_itself(tmp_path: Path) -> None:
    """🔴 Замер: показ пишет картинку шкалой 16000, а склейку тот же ffmpeg - 12288.

    Склейка уходит наружу со своим заголовком, приёмник берёт его как новое описание
    дорожек и читает им ВСЕ следующие куски - то есть чужая шкала уводит не одну склейку,
    а весь хвост показа.
    """
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)
    sound = tmp_path / "init.mp4"
    sound.write_bytes(_show_head(16000))

    merge_tracks(video, audio, dst, container=FMP4, heads=(None, sound), run=ffmpeg.run)
    command = ffmpeg.seen[0]

    assert command[command.index("-video_track_timescale") + 1] == "16000"


def test_a_show_that_cannot_be_asked_about_its_scale_is_not_guessed_at(tmp_path: Path) -> None:
    """Заголовка показа нет - шкала не выдумывается: муксер остаётся при своём умолчании."""
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)

    merge_tracks(video, audio, dst, container=FMP4, run=ffmpeg.run)

    assert "-video_track_timescale" not in ffmpeg.seen[0]


def test_the_scale_of_the_show_is_not_asked_of_mpegts_at_all(tmp_path: Path) -> None:
    """У mpegts шкалы дорожек нет вовсе, и склейка там собирается как собиралась."""
    ffmpeg = _Ffmpeg()
    video, audio, dst = _pieces(tmp_path)
    sound = tmp_path / "init.mp4"
    sound.write_bytes(_show_head(16000))

    merge_tracks(video, audio, dst, heads=(None, sound), run=ffmpeg.run)

    assert "-video_track_timescale" not in ffmpeg.seen[0]
