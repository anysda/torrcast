"""Проверяет, что отказ прогона узнаётся по строке, а не по коду возврата."""

from __future__ import annotations

from torrcast.adapters.stream_pack.run_refusal import run_refusal


def test_a_demux_error_is_an_error_whatever_the_exit_code() -> None:
    assert run_refusal("Error during demuxing: Input/output error")
    assert run_refusal("[in#0] Error during demuxing: Input/output error\nframe= 1")


def test_a_muxer_refusing_a_stream_without_stamps_is_also_a_refusal() -> None:
    # Ровно этим ffmpeg отвечает на видео из .avi с B-кадрами, где ``pts`` первого пакета
    # пуст, - и выходит при этом то нулём, то 183 на одном и том же входе.
    assert run_refusal("[mpegts @ 0x1] first pts and dts value must be set")
    assert run_refusal("[out#0/mpegts @ 0x1] Error muxing a packet")
    assert run_refusal("[vost#0:0/copy @ 0x1] Error submitting a packet to the muxer")


def test_a_working_run_is_not_called_a_refusal() -> None:
    assert not run_refusal("")
    assert not run_refusal("frame= 1 fps=0.0 q=-1.0 size=1kB time=00:00:00.04")
    # 🔴 Отрицательная проба самого признака: предупреждение о пустых метках печатает и
    # тот прогон, который дописал все куски до конца. Признай его отказом - и щуп с
    # журналом стали бы врать про исправный .avi без B-кадров (замер: 29 границ из 29
    # измерены, а строка эта стояла в выводе каждой).
    assert not run_refusal("[segment @ 0x1] Timestamps are unset in a packet for stream 0.")
