"""Цепочка показа целиком на синтетическом ролике: упаковка → раздача → mock-приёмник.

Живая приёмка §7.2 идёт на «Моане 2» (docs/stage2.md), а регрессию ловит этот тест:
он гоняет тот же код без торрента и укладывается в секунды.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import CLIP_SECONDS
from torrcast import InfraError
from torrcast.cli import Watch as _Watch
from torrcast.cli import _Clock, _play
from torrcast.state import Config, Entry, State
from torrcast.stream import HLS_SEGMENT_SECONDS, Packer, ffmpeg_hls_command, hls_base, hls_dir


def config_for(tmp_path: Path, tls: tuple[str, str], port: int) -> Config:
    """Конфиг показа как на стенде: http по голому IP (§5 SPEC-v2), приёмник — mock.

    ``tls`` тут остаётся ради второго прогона той же цепочки по https: транспорт —
    выключенная опция, но она обязана работать, и проверяется тем же тестом.
    """
    return Config(
        receiver="mock",
        tv="127.0.0.1",
        hls_dir=str(tmp_path / "hls"),
        hls_cert=tls[0],
        hls_key=tls[1],
        hls_port=port,
        hls_readrate=0.0,  # приёмка идёт быстрее реального времени
        hls_window=0,
    )


@pytest.mark.parametrize(("transport", "port"), [("http", 18461), ("https", 18462)])
def test_mock_decodes_the_whole_stream_without_gaps(
    transport: str,
    port: int,
    clip: str,
    tls: tuple[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Приёмка §7.2 в миниатюре: от начала до конца, без дыр, CORS на месте.

    Оба транспорта гоняются одной и той же цепочкой: http — рабочий дефолт (§5 SPEC-v2),
    https — выключенная опция, которая обязана оставаться живой.
    """
    config = config_for(tmp_path, tls, port)
    config.transport = transport  # type: ignore[assignment]
    assert _play(config, clip, audio=0, about="тест", clock=_Clock()) == 0
    printed = capsys.readouterr().out
    assert "→ ТВ" in printed
    assert "разрывов 0" in printed and "без CORS 0" in printed
    decoded = float(printed.split("декодировано ")[1].split(" ")[0])
    # Допуск ровно в один сегмент: если ENDLIST попадает в ту же перезагрузку плейлиста,
    # что и последний сегмент, hls-демуксер ffmpeg молча заканчивает на предыдущем.
    # Воспроизводится и на голом http.server, то есть это не наш сервер (docs/stage3.md).
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "приёмник встал посреди показа"
    assert not list(Path(config.hls_dir).glob("*.ts")), "сегменты убраны за собой"


def test_audio_is_always_reencoded_to_aac_stereo(clip: str, tmp_path: Path) -> None:
    """Источник — AC3 5.1; на выходе обязан быть AAC stereo, видео — тот же H.264 (§3, §9)."""
    out = hls_dir(str(tmp_path / "hls"))
    packer = Packer.start(ffmpeg_hls_command(clip, 0, str(out), readrate=0.0), out, window=0)
    packer.manifest()
    deadline = time.monotonic() + 60
    while packer.poll() is None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert packer.poll() == 0, packer.why()

    segment = sorted(out.glob("*.ts"))[0]
    streams = {s["codec_type"]: s for s in _probe(segment)}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    assert streams["audio"]["channels"] == 2
    packer.stop()


def test_torn_off_packing_is_an_honest_infra_error(
    clip: str, tls: tuple[str, str], tmp_path: Path
) -> None:
    """Обрыв ffmpeg посреди показа = наша ошибка кодом 2, и ничего не течёт (§5)."""
    config = config_for(tmp_path, tls, 18463)
    config.hls_readrate = 1.0  # реальное время: есть куда вклиниться посреди показа
    killer = threading.Thread(target=_kill_when_playing, args=(config, str(tmp_path)), daemon=True)
    killer.start()
    try:
        with pytest.raises(InfraError) as caught:
            _play(config, clip, audio=0, about="тест", clock=_Clock())
    finally:
        killer.join(timeout=30)
    assert "упаковка оборвалась: убит сигналом 9" in str(caught.value)
    assert not list(Path(config.hls_dir).glob("*.ts")), "сегменты убраны даже после аварии"
    assert not _alive(str(tmp_path)) and not _alive(hls_base(config)), "процессы не текут"


def _probe(path: Path) -> list[dict[str, Any]]:
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    streams: list[dict[str, Any]] = json.loads(done.stdout)["streams"]
    return streams


def _kill_when_playing(config: Config, pattern: str) -> None:
    """Дождаться, что показ реально идёт (два сегмента в манифесте), и снести ffmpeg."""
    manifest = Path(config.hls_dir) / "index.m3u8"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if manifest.exists() and manifest.read_text().count(".ts") >= 2:
            break
        time.sleep(0.2)
    subprocess.run(["pkill", "-9", "-f", pattern], check=False)


def _alive(pattern: str) -> bool:
    done = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
    return bool(done.stdout.strip())


class _FakeProc:
    """Процесс упаковки: умеет ровно то, что от него нужно показу. Сигналов остановки у
    него нет вовсе — попытка придержать упаковку SIGSTOP'ом развалила бы тест.
    """

    def __init__(self) -> None:
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.code = -15

    def wait(self, timeout: float | None = None) -> int:
        return -15


class _FakeReceiver:
    """Приёмник по сценарию: очередь состояний, как их отдаёт живой Q70D."""

    def __init__(self, script: list[tuple[float, str]]) -> None:
        self.script = script

    def play(self, url: str, title: str = "") -> None:
        pass

    def stop(self) -> None:
        pass

    def position(self) -> Any:
        from torrcast.cast import Position

        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 0.0, state in {"PLAYING", "BUFFERING"}, state)


def _packer_with_manifest(tmp_path: Path) -> Any:
    """Упаковка с готовым манифестом на 6 сегментов по 10 с; файлов на диске нет."""
    out = hls_dir(str(tmp_path / "hls"))
    lines = ["#EXTM3U"]
    for number in range(6):
        lines += ["#EXTINF:10.000000,", f"index{number}.ts"]
    (out / "index.m3u8").write_text("\n".join(lines) + "\n")
    return Packer(proc=_FakeProc(), out=out, window=0)  # type: ignore[arg-type]


def test_a_rewind_deeper_than_the_window_repacks_instead_of_404(tmp_path: Path) -> None:
    """§6 SPEC-v2: назад за окно показ не падает, а возвращает секунду для перепаковки."""
    from torrcast.cli import _hold
    from torrcast.stream import HlsServer

    packer = _packer_with_manifest(tmp_path)
    server = HlsServer(packer.out, port=0)
    server._misses.append("index3.ts")  # раздача уже ответила приёмнику 404
    receiver = _FakeReceiver([(45.0, "PLAYING")])
    assert _hold(receiver, packer, server) == 30.0, "перепаковка ровно с начала сегмента"


def test_a_pause_on_the_remote_stops_packing_and_resumes_where_it_stood(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Пауза пультом: упаковку гасим (иначе tmpfs набивается впрок), показ остаётся жив,
    а возврат к показу перепаковывает поток с той же секунды.
    """
    from torrcast import cli
    from torrcast.stream import HlsServer

    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0.0)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    packer = _packer_with_manifest(tmp_path)
    server = HlsServer(packer.out, port=0)
    receiver = _FakeReceiver([(42.0, "PAUSED"), (42.0, "PAUSED"), (42.0, "PLAYING")])

    assert cli._hold(receiver, packer, server) == 42.0
    assert packer.halted and packer.poll() == -15, "ffmpeg завершён, а не остановлен сигналом"
    assert "пауза на пульте" in capsys.readouterr().out


def test_resume_starts_from_the_offset_and_ends_as_watched(
    clip: str, tls: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    """Тот же показ, но с середины: ffmpeg стартует с `-ss`, приёмник декодирует остаток,
    сторож кладёт в state абсолютную позицию, а на 95 % пишет «досмотрено» (§2.3, §2.4).
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    key, offset = "movie:ролик:2026", 5.0
    # Длительность занижена на сегмент — по той же причине, что и допуск выше: хвост HLS
    # у клиента может отвалиться, а проверяем мы тут переход «досмотрено», а не хвост.
    entry = Entry(title="ролик", magnet="magnet:?xt=1", pos=offset, dur=CLIP_SECONDS - 4.0)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, offset=offset, every=0.0)

    config = config_for(tmp_path, tls, 18465)
    assert _play(config, clip, audio=0, about="тест", clock=_Clock(), watch=watch) == 0

    printed = capsys.readouterr().out
    decoded = float(printed.split("декодировано ")[1].split(" ")[0])
    assert decoded <= CLIP_SECONDS - offset + 1, "показ начался с позиции, а не сначала"
    assert decoded >= CLIP_SECONDS - offset - HLS_SEGMENT_SECONDS, "показ оборвался"
    assert "досмотрено" in printed
    saved = State.load().get(key)
    assert saved is not None and saved.done and saved.pos == 0.0
