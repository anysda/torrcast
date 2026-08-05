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
from torrcast.stream import HLS_SEGMENT_SECONDS, Feed, Packer, ffmpeg_hls_command, hls_base, hls_dir


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
    assert _play(config, clip, 0, "тест", _Clock(), duration=float(CLIP_SECONDS)) == 0
    printed = capsys.readouterr().out
    assert "— на ТВ" in printed
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
    packer = Packer.start(ffmpeg_hls_command(clip, 0, str(out), readrate=0.0), out)
    deadline = time.monotonic() + 60
    while packer.poll() is None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert packer.poll() == 0, packer.why()

    segment = sorted(out.glob("v*.ts"))[0]
    streams = {s["codec_type"]: s for s in _probe(segment)}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    assert streams["audio"]["channels"] == 2
    packer.stop()


def test_packing_torn_off_again_and_again_is_an_honest_infra_error(
    clip: str, tls: tuple[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Обрыв упаковки показ переживает, но не бесконечно (§5).

    Один обрыв — не авария: TorrServer под просевшим роем закрывает вход, ffmpeg честно
    умирает, и показ пакует заново с того места, где стоит приёмник. А вот источник,
    который рвётся раз за разом, обязан кончиться ошибкой кодом 2, а не вечным кругом.
    """
    config = config_for(tmp_path, tls, 18463)
    config.hls_readrate = 1.0  # реальное время: есть куда вклиниться посреди показа
    killer = threading.Thread(target=_kill_when_playing, args=(config, str(tmp_path)), daemon=True)
    killer.start()
    try:
        with pytest.raises(InfraError) as caught:
            _play(config, clip, 0, "тест", _Clock(), duration=float(CLIP_SECONDS))
    finally:
        killer.join(timeout=30)
    assert "упаковка оборвалась: убит сигналом 9" in str(caught.value)
    assert "начинаю заново" in capsys.readouterr().out, "обрыв показ переживает молча"
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
    """Сносить упаковку, как только она поднимется, — и так пока показ не сдастся."""
    out = Path(config.hls_dir)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if list(out.glob("v*.ts")):
            subprocess.run(["pkill", "-9", "-f", pattern], check=False)
        time.sleep(0.3)


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

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self) -> None:
        pass

    def position(self) -> Any:
        from torrcast.cast import Position

        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 0.0, state in {"PLAYING", "BUFFERING"}, state)


def _feed_with_segments(tmp_path: Path) -> Feed:
    """Упаковка на 60 готовых сегментов сетки; ffmpeg за ней настоящий не стоит."""
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(60):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = Feed(source="", audio=0, out=out, duration=7200.0, keep=40.0, wait=0.0)
    feed.packer = Packer(proc=_FakeProc(), out=out, first=0)  # type: ignore[arg-type]
    return feed


def test_the_show_sweeps_ram_behind_the_receiver_while_it_plays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Показ следит ровно за двумя вещами: жива ли упаковка и что убрать из tmpfs.

    Перемотку он больше не ловит вовсе — приёмник видит весь фильм и мотает сам (§2.1
    SPEC-v2), а раздача пакует то место, которое он попросил.
    """
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    feed = _feed_with_segments(tmp_path)
    receiver = _FakeReceiver([(200.0, "PLAYING"), (0.0, "IDLE")])

    cli._hold(receiver, feed)

    left = sorted(int(path.name[1:-3]) for path in feed.out.glob("v*.ts"))
    assert left == list(range(40, 60)), "позади показа держим окно, остальное — из RAM"


def test_a_pause_on_the_remote_stops_packing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Пауза пультом: упаковку гасим (иначе tmpfs набивается впрок), показ остаётся жив.

    Возобновлять её показу не нужно: человек снимет паузу, приёмник попросит следующий
    сегмент, и раздача начнёт паковать с этого самого места сама.
    """
    from torrcast import cli

    monkeypatch.setattr(cli, "PAUSE_SECONDS", 0.0)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    feed = _feed_with_segments(tmp_path)
    receiver = _FakeReceiver([(42.0, "PAUSED"), (42.0, "PAUSED"), (0.0, "IDLE")])

    cli._hold(receiver, feed)

    assert feed.halted() and feed.packer is not None and feed.packer.poll() == -15, (
        "ffmpeg завершён, а не остановлен сигналом"
    )
    assert "пауза на пульте" in capsys.readouterr().out


def test_a_finished_packer_is_not_a_crash_but_a_serial_one_gives_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Конец входа и обрыв — разные вещи, и показ обязан их различать.

    Код 0 — фильм упакован до конца, падать не с чего. Обрыв — повод начать заново с того
    места, где стоит приёмник; но если рвётся раз за разом, показ сдаётся честной строкой,
    а не крутит круг вечно.
    """
    feed = _feed_with_segments(tmp_path)
    assert feed.packer is not None
    monkeypatch.setattr(Feed, "restart", lambda self, slot: None)

    feed.packer.proc.code = 0  # type: ignore[attr-defined]
    assert feed.segment(70) is None and feed.trouble() == "", "дошли до конца фильма"

    feed.packer.proc.code = -9  # type: ignore[attr-defined]
    for _ in range(feed.limit):
        feed.segment(70)
    assert feed.trouble() == "", "обрыв переживаем молча, пока попытки не кончились"

    feed.segment(70)
    assert feed.trouble() == "убит сигналом 9"


def test_resume_starts_from_the_offset_and_ends_as_watched(
    clip: str, tls: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    """Тот же показ, но с середины: ffmpeg стартует с `-ss`, приёмник декодирует остаток,
    сторож кладёт в state абсолютную позицию, а на 95 % пишет «досмотрено» (§2.3, §2.4).
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    key, offset = "movie:ролик:2026", 8.0
    # Длительность занижена на сегмент — по той же причине, что и допуск выше: хвост HLS
    # у клиента может отвалиться, а проверяем мы тут переход «досмотрено», а не хвост.
    entry = Entry(title="ролик", magnet="magnet:?xt=1", pos=offset, dur=CLIP_SECONDS - 4.0)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    config = config_for(tmp_path, tls, 18465)
    assert _play(config, clip, 0, "тест", _Clock(), watch=watch) == 0

    printed = capsys.readouterr().out
    decoded = float(printed.split("декодировано ")[1].split(" ")[0])
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "показ оборвался"
    assert f"упаковка с {offset:.0f} с" in printed, "показ начался с позиции, а не сначала"
    assert "досмотрено" in printed
    saved = State.load().get(key)
    assert saved is not None and saved.done and saved.pos == 0.0
