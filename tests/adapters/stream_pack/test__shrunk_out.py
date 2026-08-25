"""Что уходит наружу от ужатия на месте: склейка со звуком копии или ужатие как есть."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from torrcast.adapters.stream_pack._shrunk_out import _shrunk_out
from torrcast.domain.segment_container import FMP4


def _has_key(piece: Path) -> bool:
    """Кусок начинается с опорного кадра: на стенде это знают, а не спрашивают ffprobe."""
    return False


def _lay(where: Path, name: str, size: int = 16) -> Path:
    path = where / name
    path.write_bytes(b"x" * size)
    return path


def test_the_shrunk_piece_goes_out_with_the_audio_of_the_copy(tmp_path: Path) -> None:
    """🔴 Наружу идёт картинка ужатия и звук копии, а не звук второго прогона ffmpeg.

    Замер на живом показе: у соседей-копий стык звука +0.021333 с (один кадр AAC), у
    ужатого места на входе +0.074667 (дыра 53 мс), на выходе -0.053334 (метки назад).
    """
    seen: list[tuple[str, str]] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((video.name, audio.name))
        dst.write_bytes(b"m" * 20)
        return True

    copy, shrunk = _lay(tmp_path, "v7.ts", 100), _lay(tmp_path, "spare7.ts", 18)

    out = _shrunk_out(
        tmp_path, 7, copy, shrunk, 50, merge=merge, shift_of=lambda *a: 0.0, keyless=_has_key
    )

    assert seen == [("spare7.ts", "v7.ts")], "звук ужатого места взят не у копии"
    assert out.name == "mix7.ts" and out.read_bytes() == b"m" * 20


def test_the_shift_between_the_two_passes_reaches_the_merge(tmp_path: Path) -> None:
    """Сдвиг лент копии и ужатия доезжает до склейки: без него стык уедет на кадр."""
    shifts: list[float] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        shifts.append(kwargs["shift"])
        dst.write_bytes(b"m")
        return True

    copy, shrunk = _lay(tmp_path, "v3.ts"), _lay(tmp_path, "spare3.ts")

    _shrunk_out(
        tmp_path, 3, copy, shrunk, 50, merge=merge, shift_of=lambda *a: 0.0417, keyless=_has_key
    )

    assert shifts == [0.0417]


def test_a_merge_that_did_not_happen_leaves_the_bare_shrink(tmp_path: Path) -> None:
    """Склейки нет - наружу голое ужатие: кусок без звука хуже стыка со звуком."""
    copy, shrunk = _lay(tmp_path, "v1.ts"), _lay(tmp_path, "spare1.ts")

    out = _shrunk_out(
        tmp_path,
        1,
        copy,
        shrunk,
        50,
        merge=lambda *a, **k: False,
        shift_of=lambda *a: 0.0,
        keyless=_has_key,
    )

    assert out == shrunk and not (tmp_path / "mix1.ts").exists()


def test_a_merge_heavier_than_the_ceiling_is_thrown_away(tmp_path: Path) -> None:
    """Склейка за потолком приёмника не уходит никуда: остаётся картинка ужатия."""

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        dst.write_bytes(b"m" * 80)
        return True

    copy, shrunk = _lay(tmp_path, "v2.ts"), _lay(tmp_path, "spare2.ts")

    out = _shrunk_out(
        tmp_path, 2, copy, shrunk, 50, merge=merge, shift_of=lambda *a: 0.0, keyless=_has_key
    )

    assert out == shrunk, "склейка тяжелее потолка ушла бы приёмнику"
    assert not (tmp_path / "mix2.ts").exists(), "склейка за потолком осталась лежать"


def test_a_piece_without_a_key_frame_is_never_merged(tmp_path: Path) -> None:
    """🔴 TC-698. Склейка идёт ``-c copy``: у куска без опорного кадра она съест картинку.

    Такой кусок приходит от кодировщика, доехавшего, пока ужатие ждало замка. Ему
    остаётся прежний путь - наружу как есть, со своим звуком и своим стыком.
    """
    tried: list[str] = []
    copy, shrunk = _lay(tmp_path, "v9.ts"), _lay(tmp_path, "spare9.ts")

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        tried.append(video.name)
        return True

    out = _shrunk_out(
        tmp_path,
        9,
        copy,
        shrunk,
        50,
        merge=merge,
        shift_of=lambda *a: 0.0,
        keyless=lambda piece: True,
    )

    assert out == shrunk and tried == [], "кусок без опорного кадра ушёл в склейку"


def test_the_merge_of_a_shrunk_place_is_named_and_muxed_by_the_container(
    tmp_path: Path,
) -> None:
    """Имя склейки и её муксер - оба из контейнера показа, а не из умолчания завода."""
    seen: list[tuple[str, object]] = []

    def merge(video: Path, audio: Path, dst: Path, **kwargs: Any) -> bool:
        seen.append((dst.name, kwargs.get("container")))
        dst.write_bytes(b"m" * 20)
        return True

    copy, shrunk = _lay(tmp_path, "v7.m4s", 100), _lay(tmp_path, "spare7.m4s", 18)

    out = _shrunk_out(
        tmp_path,
        7,
        copy,
        shrunk,
        50,
        FMP4,
        merge=merge,
        shift_of=lambda *a: 0.0,
        keyless=_has_key,
    )

    assert seen == [("mix7.m4s", FMP4)]
    assert out.name == "mix7.m4s"
