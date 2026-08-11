"""Цепочка показа целиком на синтетическом ролике: упаковка → раздача → mock-приёмник.

Живьём это проверяется настоящим фильмом на телевизоре, а регрессию ловит этот тест:
он гоняет тот же код без торрента и укладывается в секунды.

Здесь же живёт единственная проверка сетки сегментов, которую нельзя сделать на бумаге:
кусок под именем ``vN`` обязан быть одним и тем же местом фильма, с какого бы места ни
начали паковать. Проверяется это настоящим ffmpeg на настоящем ролике — арифметикой
границ (tests/test_hls.py) доказывается только то, что мы его об этом попросили.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pytest

from tests.conftest import CLIP_SECONDS, FakeProc, fake_packer, free_port
from torrcast import InfraError
from torrcast.cast import MockReceiver, Position
from torrcast.cli import Watch as _Watch
from torrcast.cli import _Clock, _play
from torrcast.state import Config, Entry, State
from torrcast.stream import (
    HLS_SEGMENT_SECONDS,
    PACK_DIR,
    Feed,
    Grid,
    Packer,
    ffmpeg_pack_command,
    hls_base,
    hls_dir,
    mark_playing,
    pack_start,
    playing_flag,
    segment_name,
)


def test_a_release_without_a_video_file_is_a_verdict_not_an_infra_error() -> None:
    """«Образ диска» - приговор раздаче (:class:`NotFoundError`), а не сбой инфраструктуры.

    Типом этого отказа пользуется отбор (:func:`~torrcast.cli._silenced`): InfraError
    читается молчанием роя, и раздача-журнал («lainzine 1-5» по запросу «lain», TC-399)
    числилась бы неотозвавшейся, хотя про неё известно всё.
    """
    from torrcast import NotFoundError
    from torrcast.stream import TorrFile, pick_video_file

    with pytest.raises(NotFoundError, match="нет отдельного видеофайла"):
        pick_video_file([TorrFile(0, "VIDEO_TS.VOB", 4 * 1024**3), TorrFile(1, "cover.jpg", 1)])


def config_for(tmp_path: Path, tls: tuple[str, str]) -> Config:
    """Конфиг показа как в бою: http по голому IP, приёмник — mock.

    ``tls`` тут остаётся ради второго прогона той же цепочки по https: транспорт —
    выключенная опция, но она обязана работать, и проверяется тем же тестом.

    Порт берётся свободный (:func:`tests.conftest.free_port`), а не константой: показ
    поднимает настоящую раздачу, и с прибитым номером два прогона рядом дрались бы за
    bind. Номер порта ни одному тесту ниже не интересен - он спрашивается у конфига.

    ``hls_keyframes=False``: карта опорных кадров снимается Range-запросами по HTTP
    (:mod:`torrcast.mkv`), а источник у этих тестов — файл на диске, читать который тем же
    способом неоткуда. Сетка по кадрам проверяется отдельно, ffmpeg'ом, в
    :func:`test_the_same_name_holds_the_same_piece_wherever_packing_started`.
    """
    return Config(
        receiver="mock",
        tv="127.0.0.1",
        hls_dir=str(tmp_path / "hls"),
        hls_cert=tls[0],
        hls_key=tls[1],
        hls_port=free_port(),
        hls_readrate=0.0,  # приёмка идёт быстрее реального времени
        hls_keyframes=False,
        # Прогрев на диск - отдельный тракт со своими тестами (`test_warm.py`). Здесь
        # проверяется живая упаковка, и второй ffmpeg рядом с ней только мешал бы мерить.
        warm=False,
    )


def _keys_of(clip: str) -> list[float]:
    """Опорные кадры ролика — то же, что показ берёт из индекса mkv (:mod:`torrcast.mkv`).

    Здесь их можно взять честным перебором пакетов: ролик короткий и лежит на диске. На
    фильме через рой так делать нельзя — ради этого и написан разбор Cues.
    """
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", clip],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return [float(line.rstrip(",")) for line in done.stdout.split() if line.strip(",")]


def _pack(clip: str, grid: Grid, slot: int, out: Path) -> Packer:
    """Один живой прогон упаковки с сегмента ``slot`` до конца входа.

    Место старта не угадывается, а меряется (:func:`pack_start`) — ровно как в показе:
    ``-ss`` уводит ffmpeg на опорный кадр не позже запрошенного, и без этого числа
    границы сегментов уехали бы относительно фильма.
    """
    run = out / PACK_DIR
    at = pack_start(clip, grid.start(slot))
    command = ffmpeg_pack_command(clip, 0, str(run), grid, slot, at, readrate=0.0)
    packer = Packer.start(command, out, run, slot)
    deadline = time.monotonic() + 120
    while packer.poll() is None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert packer.poll() == 0, packer.why()
    packer.publish()
    return packer


def _video(path: Path) -> str:
    """md5 битстрима видео куска — **без** меток времени.

    Сравнивать метки нельзя, и это не придирка: при упаковке от нуля ffmpeg не пускает dts
    ниже нуля и сдвигает весь фильм на кадр вперёд, а при упаковке из середины метки
    остаются исходными. Кадры при этом те же самые — что и требуется доказать.
    """
    command = ["ffmpeg", "-v", "error", "-i", str(path),
               "-map", "0:v", "-c", "copy", "-f", "h264", "-"]  # fmt: skip
    done = subprocess.run(command, capture_output=True, check=True)
    return hashlib.md5(done.stdout).hexdigest()


@pytest.mark.parametrize("transport", ["http", "https"])
def test_mock_decodes_the_whole_stream_without_gaps(
    transport: str,
    clip: str,
    tls: tuple[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Показ в миниатюре: от начала до конца, без дыр, CORS на месте.

    Оба транспорта гоняются одной и той же цепочкой: http — рабочий дефолт,
    https — выключенная опция, которая обязана оставаться живой.
    """
    config = config_for(tmp_path, tls)
    config.transport = transport  # type: ignore[assignment]
    assert _play(config, clip, 0, "тест", _Clock(), duration=float(CLIP_SECONDS)) == 0
    printed = capsys.readouterr().out
    assert "- на ТВ" in printed
    assert "разрывов 0" in printed and "без CORS 0" in printed
    decoded = float(printed.split("декодировано ")[1].split(" ")[0])
    # Допуск ровно в один сегмент: если ENDLIST попадает в ту же перезагрузку плейлиста,
    # что и последний сегмент, hls-демуксер ffmpeg молча заканчивает на предыдущем.
    # Воспроизводится и на голом http.server, то есть дело не в нашем сервере.
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "приёмник встал посреди показа"
    assert not list(Path(config.hls_dir).glob("*.ts")), "сегменты убраны за собой"


def test_a_source_the_receiver_cannot_decode_is_recoded_from_the_first_segment(
    clip_hevc: str,
    tls: tuple[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """HEVC-файл уезжает на приёмник H.264 целиком — и с первого же куска.

    Ровно тут и была латентная петля: решение о перекоде принималось посегментно, по весу
    и битрейту, поэтому лёгкие куски уходили HEVC как есть. На живом Q70D это 24 с
    картинки и вечный BUFFERING на границе первого такого куска (замер 07-08, §3 спеки).
    Проверяем не намерение, а факт: ffprobe каждого выложенного сегмента.
    """
    assert _probe(Path(clip_hevc))[0]["codec_name"] == "hevc", "источник обязан быть HEVC"
    config = config_for(tmp_path, tls)
    kept: list[Path] = []
    where = tmp_path / "kept"
    where.mkdir()
    stop = threading.Event()
    watcher = threading.Thread(target=_grab_segments, args=(config, where, kept, stop), daemon=True)
    watcher.start()
    try:
        played = _play(
            config, clip_hevc, 0, "тест", _Clock(), duration=float(CLIP_SECONDS), codec="hevc"
        )
    finally:
        stop.set()
        watcher.join(timeout=10)

    printed = capsys.readouterr().out
    assert played == 0
    assert "видео hevc - перекодирую на ходу целиком" in printed, "решение говорится вслух"
    assert "тяжёлых кусков" not in printed, "посегментный кодировщик тут не поднимается"
    assert "разрывов 0" in printed
    decoded = float(printed.split("декодировано ")[1].split(" ")[0])
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "приёмник встал посреди показа"
    assert kept, "ни одного выложенного сегмента поймать не удалось"
    for path in kept:
        codecs = {s["codec_type"]: s["codec_name"] for s in _probe(path)}
        assert codecs["video"] == "h264", f"{path.name}: на ТВ уехал {codecs['video']}"
        assert codecs["audio"] == "aac", f"{path.name}: звук всегда AAC"


def _grab_segments(
    config: Config, where: Path, kept: list[Path], stop: threading.Event, limit: int = 3
) -> None:
    """Складывать копии выложенных сегментов, пока показ идёт: после него их не будет.

    Показ убирает за собой tmpfs (это отдельное требование и отдельный тест), поэтому
    спросить готовый кусок задним числом нельзя — только на ходу.
    """
    import shutil

    out = Path(config.hls_dir)
    while not stop.is_set() and len(kept) < limit:
        for path in sorted(out.glob("v*.ts")):
            dst = where / path.name
            if dst.exists() or len(kept) >= limit:
                continue
            with contextlib.suppress(OSError):
                shutil.copy2(path, dst)
                kept.append(dst)
        stop.wait(0.2)


def test_the_same_name_holds_the_same_piece_wherever_packing_started(
    clip: str, tmp_path: Path
) -> None:
    """Живьём: имя сегмента — это место в фильме, а не порядковый номер.

    Ровно это и ломалось раньше: сегментный муксер отсчитывал границы от первого
    пакета прогона, поэтому после каждой перемотки под тем же именем лежало другое место,
    манифест врал, а уже упакованное приходилось выбрасывать. Теперь границы абсолютные —
    и два прогона, начатые в разных местах, обязаны дать под одним именем один и тот же
    кусок фильма.

    Побайтно сравнивается **видео**: метки времени у прогона от нуля на кадр больше
    (ffmpeg не пускает dts ниже нуля), и сравнивать контейнер целиком было бы враньём.
    """
    grid = Grid.on_keyframes(_keys_of(clip), float(CLIP_SECONDS), float(HLS_SEGMENT_SECONDS))
    assert grid.on_keys and grid.count > 4, "сетка вышла слишком мелкой, сравнивать нечего"
    slot = 3

    head = _pack(clip, grid, 0, hls_dir(str(tmp_path / "head")))
    tail = _pack(clip, grid, slot, hls_dir(str(tmp_path / "tail")))
    try:
        assert head.drift(grid) < 0.05, "прогон от нуля нарезал не то, что обещал манифест"
        assert tail.drift(grid) < 0.05, "прогон с середины нарезал не то, что обещал манифест"
        assert not (tail.out / segment_name(slot - 1)).exists(), "докатка вышла наружу"

        for number in range(slot, grid.count):
            name = segment_name(number)
            assert (tail.out / name).exists(), f"{name}: прогон с середины его не выложил"
            assert _video(head.out / name) == _video(tail.out / name), f"{name}: разные куски"
    finally:
        head.stop()
        tail.stop()


def test_audio_is_always_reencoded_to_aac_stereo(clip: str, tmp_path: Path) -> None:
    """Источник — AC3 5.1; на выходе обязан быть AAC stereo, видео — тот же H.264."""
    out = hls_dir(str(tmp_path / "hls"))
    packer = _pack(clip, Grid.uniform(float(CLIP_SECONDS)), 0, out)

    segment = sorted(out.glob("v*.ts"))[0]
    streams = {s["codec_type"]: s for s in _probe(segment)}
    assert streams["video"]["codec_name"] == "h264"
    assert streams["audio"]["codec_name"] == "aac"
    assert streams["audio"]["channels"] == 2
    packer.stop()


def test_packing_torn_off_again_and_again_is_an_honest_infra_error(
    clip: str, tls: tuple[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Обрыв упаковки показ переживает, но не бесконечно.

    Один обрыв — не авария: TorrServer под просевшим роем закрывает вход, ffmpeg честно
    умирает, и показ пакует заново с того места, где стоит приёмник. А вот источник,
    который рвётся раз за разом, обязан кончиться ошибкой кодом 2, а не вечным кругом.
    """
    config = config_for(tmp_path, tls)
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
    """Сносить упаковку, как только она поднимется, — и так пока показ не сдастся.

    Ждём кусок в каталоге прогона, а не снаружи: наружу он попадёт только после
    :meth:`Packer.publish`, и к тому времени можно не успеть вклиниться.
    """
    out = Path(config.hls_dir)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if list(out.glob("**/v*.ts")):
            for pid in _own_pids(pattern):  # только свои: соседний прогон не наше дело
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
        time.sleep(0.3)


#: Метка этого прогона. Она попадает в окружение всех потомков (ffmpeg поднимается
#: обычным ``Popen`` без ``env``), и по ней свои процессы отличаются от чужих.
_RUN_MARK: Final = f"TORRCAST_TEST_RUN={os.getpid()}-{uuid.uuid4().hex}"
os.environ["TORRCAST_TEST_RUN"] = _RUN_MARK.split("=", 1)[1]


def _own_pids(pattern: str) -> list[int]:
    """Свои живые процессы, у которых ``pattern`` есть в командной строке.

    /proc читается руками, а не ``pgrep -f``, и на то две причины. Первая — соседний
    прогон: порт и каталог показа у него те же, так что по одной командной строке его
    процессы не отличить от наших, и тест краснел на чужом ffmpeg. Вторая — сам поиск:
    ``pgrep -f`` находит и себя, и запущенный рядом такой же ``pgrep`` с тем же
    шаблоном. Метка прогона (:data:`_RUN_MARK`) снимает обе.
    """
    mine = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
            if pattern not in raw.replace(b"\0", b" ").decode("utf-8", "replace"):
                continue
            environ = (entry / "environ").read_bytes()
        except OSError:
            continue  # процесс умер под руками или он не наш
        if _RUN_MARK.encode() in environ.split(b"\0"):
            mine.append(int(entry.name))
    return mine


def _alive(pattern: str) -> bool:
    return bool(_own_pids(pattern))


class _FakeReceiver:
    """Приёмник по сценарию: очередь состояний, как их отдаёт живой Q70D."""

    def __init__(self, script: list[tuple[float, str]]) -> None:
        self.script = script

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self, quit_app: bool = False) -> None:
        pass

    def position(self, front: float = 0.0) -> Any:
        from torrcast.cast import Position

        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 0.0, state in {"PLAYING", "BUFFERING"}, state)


def _feed_with_segments(tmp_path: Path) -> Feed:
    """Упаковка на 60 готовых сегментов ровной сетки; ffmpeg за ней настоящий не стоит."""
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(60):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(7200.0), keep=40.0, wait=0.0)
    feed.packer = fake_packer(out, first=0)
    return feed


def test_the_show_sweeps_ram_behind_the_receiver_while_it_plays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Показ следит ровно за двумя вещами: жива ли упаковка и что убрать из tmpfs.

    Перемотку он больше не ловит вовсе — приёмник видит весь фильм и мотает сам,
    а раздача пакует то место, которое он попросил.
    """
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    feed = _feed_with_segments(tmp_path)
    receiver = _FakeReceiver([(200.0, "PLAYING"), (0.0, "IDLE")])

    cli._hold(receiver, feed)

    edge = feed.grid.slot_at(160.0)
    left = sorted(int(path.name[1:-3]) for path in feed.out.glob("v*.ts"))
    assert left == list(range(edge, 60)), "позади показа держим окно, остальное - из RAM"


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


def test_the_diagnostic_remote_reaches_the_receiver_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Диагностический пульт (``TORRCAST_CTL``): команда доезжает до приёмника ровно раз.

    Проверяется то, ради чего он написан: seek идёт **владеющим сендером** (тот же объект,
    что держит показ), файл съедается, и повторно та же команда не исполняется — иначе
    одна опечатка мотала бы фильм на каждом опросе.
    """
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    seen: list[tuple[str, float]] = []

    class _Remote(_FakeReceiver):
        def seek(self, pos: float) -> None:
            seen.append(("seek", pos))

        def pause(self) -> None:
            seen.append(("pause", 0.0))

        def resume(self) -> None:
            seen.append(("play", 0.0))

    ctl = tmp_path / "ctl"
    ctl.write_text("seek 1200.5", "utf-8")
    monkeypatch.setenv(cli.CTL_ENV, str(ctl))
    feed = _feed_with_segments(tmp_path)
    receiver = _Remote([(200.0, "PLAYING"), (210.0, "PLAYING"), (0.0, "IDLE")])

    cli._hold(receiver, feed)

    assert seen == [("seek", 1200.5)], "команда исполнена один раз и владеющим сендером"
    assert not ctl.exists(), "команда одноразовая - файл съеден"


def test_the_diagnostic_remote_is_absent_without_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Без ``TORRCAST_CTL`` пульта нет вовсе: на счастливом пути этот код не работает."""
    from torrcast import cli

    monkeypatch.delenv(cli.CTL_ENV, raising=False)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    ctl = tmp_path / "ctl"
    ctl.write_text("seek 1200.5", "utf-8")
    feed = _feed_with_segments(tmp_path)

    cli._hold(_FakeReceiver([(200.0, "PLAYING"), (0.0, "IDLE")]), feed)

    assert ctl.read_text("utf-8") == "seek 1200.5", "файл не читается и не съедается"


class _Ticker:
    """Часы, которые двигает только сон показа: опрос раз в 2 с, как в жизни.

    ``ticks`` - те, для кого время идёт вместе с часами: декодер заглушки за сон показа
    успевает продвинуться ровно на столько же секунд, на сколько сдвинулись часы.
    """

    def __init__(self) -> None:
        self.now = 1000.0
        self.ticks: list[Callable[[float], None]] = []

    def sleep(self, seconds: float) -> None:
        seconds = seconds or 2.0
        self.now += seconds
        for tick in list(self.ticks):
            tick(seconds)

    def monotonic(self) -> float:
        return self.now


class _Warm:
    """Прогрев глазами показа: сколько секунд легло на диск и лёг ли фильм целиком."""

    def __init__(self, warmed: float = 600.0, done: bool = False) -> None:
        self.warmed = warmed
        self.done = done

    def feed(self, slack: float) -> None:
        pass

    def line(self) -> str:
        return "прогрето"


class _Fading:
    """Приёмник, у которого кончилось терпение: показ он бросил, но поднять себя даёт.

    Так и ведёт себя живой Samsung Q70D, когда картинка встала: медиасессия умирает через
    23.5 с (замер 09-08-2026), потратив два перезабора куска по HTTP - повторами LOAD они
    не были никогда, ``media_session_id`` при этом не менялся. После этого сессия мертва -
    состояние ``IDLE``, а позиции в ней нет вовсе, там ноль. Мир при этом продолжает жить:
    через ``back_at`` секунд темноты сеть возвращается, прогрев тащит куски и раздача
    снова читается.
    """

    def __init__(
        self,
        clock: _Ticker,
        feed: Feed,
        warmer: _Warm,
        takes: bool = True,
        at: float = 1200.0,
        dur: float = 7200.0,
        back_at: float = 0.0,
    ) -> None:
        self.clock, self.feed, self.warmer = clock, feed, warmer
        self.takes, self.at, self.dur, self.back_at = takes, at, dur, back_at
        self.began = clock.now
        self.left = 1  # один опрос показ ещё идёт, дальше приёмник его бросает
        self.replays: list[float] = []

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self, quit_app: bool = False) -> None:
        pass

    def position(self, front: float = 0.0) -> Any:
        from torrcast.cast import Position

        if self.back_at and self.clock.now - self.began >= self.back_at:
            self.feed.offline = ""  # раздача снова читается
            self.warmer.warmed += 10.0  # и прогрев потащил новые куски
        if self.left > 0:
            self.left -= 1
            return Position(self.at, self.dur, True, "PLAYING")
        return Position(0.0, self.dur, False, "IDLE")

    def replay(self, at: float) -> bool:
        self.replays.append(at)
        if not self.takes:
            return False
        # Показ поднялся и доехал до титров - дальше приёмник гаснет уже законно.
        self.at, self.left = self.dur * 0.96, 2
        return True


def _dark(
    tmp_path: Path,
    offline: str = "источник молчит дольше 45 с",
    **kwargs: Any,
) -> tuple[_Ticker, Feed, _Warm, _Fading]:
    """Общий вход всех сценариев: смотрели 20-ю минуту, сеть оборвалась, экран погас."""
    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    feed.offline = offline
    warmer = _Warm(warmed=kwargs.pop("warmed", 600.0), done=kwargs.pop("done", False))
    return clock, feed, warmer, _Fading(clock, feed, warmer, **kwargs)


def test_an_outage_longer_than_the_receivers_patience_does_not_end_the_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Обрыв длиннее терпения приёмника: экран погас - показ поднимается сам и с места.

    Замер 09-08-2026 на живом Samsung Q70D: стоящая картинка дольше 23.5 с - и медиасессия
    мертва; приложение висит на экране ещё 301 с после этого (прежние «примерно четыре
    минуты» склеивали эти два срока). Своё приёмник тратит на перезаборы куска по HTTP, а
    не на повторы LOAD. Позиция при этом честно сохранена, но экран остаётся чёрным, пока
    человек не сходит к консоли, - а продукт
    обещает обратное: показ переживает обрыв интернета.

    Проверяется всё, чем это обещание держится: пока источник молчит, LOAD в приёмник не
    летит вовсе (терпение у него своё, и жечь его впустую нельзя), а как только куски
    пошли снова, показ грузится ровно с той секунды, на которой его смотрели.
    """
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path, back_at=300.0)

    cli._hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "показ подняли, и ровно с той секунды, где смотрели"
    assert clock.now - 1000.0 >= 300.0, "до возврата сети приёмник не трогали ни разу"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00" in printed, "уход в темноту - честная строка, не молчание"
    assert "поднимаю показ с 0:20:00" in printed and "показ поднят с 0:20:00" in printed


def test_a_restored_source_spends_a_try_only_after_the_first_piece_is_ready(
    tmp_path: Path,
) -> None:
    """Ответившая служба ещё собирает метаданные и пиров - LOAD ждёт готового куска."""
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path, warmed=0.0)
    for piece in feed.out.glob("v*.ts"):
        piece.unlink()
    service = _Service(up=False)
    ready_at = clock.now + 300.0
    returned_at = clock.now + 243.0

    def source_progress(_seconds: float) -> None:
        if clock.now >= returned_at:
            service.up = True
        if clock.now >= ready_at:
            (feed.out / segment_name(feed.grid.slot_at(1200.0))).write_bytes(b"ready")

    clock.ticks.append(source_progress)

    cli._hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "готовый кусок получил одну попытку подъёма"
    assert clock.now >= ready_at, "ответ службы сам по себе попытку не потратил"


def test_a_dark_show_gives_up_after_a_limited_number_of_tries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Попыток конечное число, и между ними держится выдержка.

    Бесконечный цикл LOAD в приёмник недопустим: терпение у него своё, а экран после
    смерти сессии ещё 301 с занят его же приложением (замер; наказания за 404 при этом
    нет вовсе - ноль секунд). Сеть вернулась, а показ всё равно не встаёт - значит дело не
    в сети, и упираться дальше нечего: гаснем честно, `cast` продолжит с места.
    """
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path, takes=False, back_at=300.0)

    cli._hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0] * cli.REVIVE_TRIES, "попытки конечны и все - с места"
    assert clock.now - 1000.0 >= 300.0 + 2 * cli.REVIVE_PAUSE, "между попытками выдержка"
    printed = capsys.readouterr().out
    assert "приёмник показ не взял" in printed
    assert "показ поднять не удалось" in printed and "cast продолжит с 0:20:00" in printed


def test_a_network_that_never_returns_ends_the_show_exactly_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Сеть так и не вернулась - фолбэк: гаснем честно, ни одного LOAD в приёмник.

    Это ровно сегодняшнее поведение, и оно обязано остаться: показ кончается, позиция уже
    в состоянии, `cast` продолжит с места. Ново здесь одно - показ не уходит молча в ту же
    секунду, а ждёт сеть, пока ждать есть смысл.
    """
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path)

    expected_end = cli._hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [], "мёртвая сеть - в приёмник не ушло ни одного LOAD"
    assert expected_end, "исчерпанные попытки - ожидаемый фолбэк, а не падение юнита"
    assert clock.now - 1000.0 > cli.REVIVE_LIMIT, "ждали ровно столько, сколько обещали"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00" in printed and "cast продолжит с 0:20:00" in printed


def test_the_darkness_is_named_in_the_state_and_not_called_a_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Пока экран чёрный, это видно снаружи: отметка темноты с причиной уходит в состояние.

    Замер на живом стенде: с мёртвым источником юнит жил 902 с, и все эти минуты
    ``cast status`` отвечал «играю» - живой юнит был для него доказательством картинки.
    Доказательства в нём нет: юнит нарочно переживает смерть источника, потому что
    вернувшийся источник он поднимает сам. Правду про экран поэтому говорит сам показ, и
    кладёт он её в ту же запись, куда кладёт позицию, - другого канала наружу нет.

    Здесь играть нечем вовсе: источник мёртв, прогретого ноль. Проверяется, что отметка
    появляется не в конце, а в самой темноте, называет причину и уходит вместе с показом.
    """
    from torrcast import cli

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    warmer.warmed = 0.0  # прогретого нет - в темноте играть нечем
    entry = Entry(title="ролик", magnet=MAGNET, pos=0.0, dur=7200.0)
    watch = _Watch(key="movie:ролик:2026", entry=entry, every=0.0)
    seen: list[tuple[float, str]] = []
    clock.ticks.append(lambda _s: seen.append(_dark_mark(watch.key)))

    cli._hold(receiver, feed, watch, warmer, _supply(_Service(up=False)), clock=clock)  # type: ignore[arg-type]

    marked = [mark for mark in seen if mark[0]]
    assert marked, "темнота не названа темнотой ни разу за все 900 с"
    assert {why for _at, why in marked} == {"TorrServer не отвечает"}, "причина не та"
    assert len(marked) * 2 > cli.REVIVE_LIMIT * 0.9, "отметка появилась не сразу, а под конец"
    assert seen[0] == (0.0, ""), "у живой картинки отметки темноты нет"
    printed = capsys.readouterr().out
    assert "(TorrServer не отвечает) - картинки нет; источник не вернулся" in printed, (
        "человеку про темноту сказано числом, а не строкой «экран: … · IDLE»"
    )
    assert "погашу через 0:00:02" in printed, "не сказано, когда показ сдастся сам"
    assert printed.count("экран:") == 1, "экраном названа только живая картинка, до темноты"
    assert "показ обеспечен до" not in printed, "обеспечивать в темноте уже нечего"


def test_the_darkness_mark_goes_away_with_the_picture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сеть вернулась, показ поднят - отметки темноты в состоянии больше нет.

    Иначе ``cast status`` звал бы погасшим показ, который давно идёт: отметка обязана
    сниматься тем же, чем ставится, и в ту же секунду.
    """
    from torrcast import cli

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    clock, feed, warmer, receiver = _dark(tmp_path, back_at=300.0)
    entry = Entry(title="ролик", magnet=MAGNET, pos=0.0, dur=7200.0)
    watch = _Watch(key="movie:ролик:2026", entry=entry, every=0.0)
    seen: list[tuple[float, str]] = []
    clock.ticks.append(lambda _s: seen.append(_dark_mark(watch.key)))

    cli._hold(receiver, feed, watch, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "показ подняли - иначе проверять нечего"
    assert [mark for mark in seen if mark[0]], "темнота была и отмечена"
    assert _dark_mark(watch.key) == (0.0, ""), "картинка идёт, а запись зовёт показ погасшим"


def test_the_darkness_reason_follows_a_returning_source(tmp_path: Path) -> None:
    """Источник уже отвечает - текущая строка больше не называет его мёртвым."""
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path)
    service = _Service(up=False)
    revival = cli._Revival(supply=_supply(service), clock=clock)

    assert revival.resurrect(receiver, feed, warmer, 1200.0)  # type: ignore[arg-type]
    assert revival.why == "TorrServer не отвечает"
    service.up = True

    assert revival.resurrect(receiver, feed, warmer, 1200.0)  # type: ignore[arg-type]
    assert revival.why == "источник вернулся - жду готовности потока"


def _dark_mark(key: str) -> tuple[float, str]:
    """Отметка темноты из состояния: когда погасло и почему."""
    entry = State.load().get(key)
    return (entry.dark, entry.dark_why) if entry is not None else (0.0, "")


def test_a_warmed_movie_is_revived_without_waiting_for_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Фильм лёг на диск целиком - воскрешение не ждёт сети ни секунды: смотреть есть что."""
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path, warmed=7200.0, done=True)

    cli._hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "подняли сразу и с сохранённого места"
    assert clock.now - 1000.0 < cli.REVIVE_PAUSE, "ждать возврата сети было незачем"


def test_a_finished_movie_is_not_resurrected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Титры - не авария: досмотренный фильм гаснет и остаётся погашенным."""
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path, offline="", at=7100.0)

    cli._hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [], "конец показа не воскрешают"
    assert clock.now - 1000.0 < cli.REVIVE_PAUSE, "и не ждут на нём ни сети, ни выдержки"


class _Nudged:
    """Приёмник, застрявший в BUFFERING: сторож подвиса гонит указатель вперёд по 8 с.

    Ровно замер живого Q70D: картинка стоит на 2:39, а сторож
    (:meth:`torrcast.cast.ChromecastReceiver._nudge`) двенадцать раз прыгает вперёд, вытаскивая
    приёмник из зависания, и уводит позицию на 4:15 - на 1:36 впереди последнего кадра,
    который человек видел. Картинки всё это время нет: состояние остаётся ``BUFFERING``,
    и только его отличие от ``PLAYING`` и говорит, где кончился показ, а где начался
    указатель. Потом приёмник бросает показ насовсем.
    """

    def __init__(self, clock: _Ticker, feed: Feed, warmer: _Warm, back_at: float = 0.0) -> None:
        self.clock, self.feed, self.warmer, self.back_at = clock, feed, warmer, back_at
        self.began = clock.now
        self.seen = 159.0  # 2:39 - последний показанный кадр
        self.pos = self.seen
        self.nudges = 12
        self.shown = True
        self.replays: list[float] = []

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self, quit_app: bool = False) -> None:
        pass

    def position(self, front: float = 0.0) -> Any:
        from torrcast.cast import Position

        if self.back_at and self.clock.now - self.began >= self.back_at:
            self.feed.offline = ""
            self.warmer.warmed += 10.0
        if self.shown:  # один опрос картинка ещё идёт - его и обязана запомнить закладка
            self.shown = False
            return Position(self.seen, 7200.0, True, "PLAYING")
        if self.nudges > 0:
            self.nudges -= 1
            self.pos += 8.0  # прыжок сторожа: указатель поехал, картинка - нет
            return Position(self.pos, 7200.0, True, "BUFFERING")
        return Position(0.0, 7200.0, False, "IDLE")

    def replay(self, at: float) -> bool:
        self.replays.append(at)
        return False  # приёмник так и не вернулся: показ кончится честной темнотой


def test_the_bookmark_holds_the_last_frame_seen_not_where_the_watchdog_drove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сторож подвиса увёл указатель на 1:36 вперёд - воскресаем с последнего КАДРА.

    Замер на живом Q70D: показ встал на 2:39, сторож сделал 12 нуджей по 8 с и довёл
    указатель до 4:15, а картинки не было ни секунды из этих полутора минут. Воскрешение
    при этом точное - оно поднимает ровно ту секунду, которую ему дали, - и потому человек
    продолжал с места, которого не видел, а «Продолжить?» звало его туда же.

    Сторож здесь прав и не трогается: он вытаскивает приёмник из зависания, и прыгать ему
    есть чем только вперёд. Чинится закладка: место показа отмеряет глаз, а не указатель,
    то есть ``PLAYING``, а не ``BUFFERING``.
    """
    from torrcast import cli

    clock = _Ticker()
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    feed = _feed_with_segments(tmp_path)
    feed.offline = "источник молчит дольше 45 с"
    warmer = _Warm()
    receiver = _Nudged(clock, feed, warmer, back_at=100.0)
    entry = Entry(title="ролик", magnet=MAGNET, pos=0.0, dur=7200.0)
    watch = _Watch(key="movie:ролик:2026", entry=entry, every=0.0)

    cli._hold(receiver, feed, watch, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [159.0] * cli.REVIVE_TRIES, "поднимаем с показанного кадра"
    assert entry.pos == 159.0, "и «Продолжить?» зовёт туда же, а не на 4:15"


class _Blinking:
    """Приёмник, бросающий показ при ЖИВОМ источнике, - и молчащий после этого.

    Замер живого Q70D, из которого выросли обе проверки ниже. Первое: пока идёт темнота,
    служба раздач цела, и прогрев растёт всё это время - то есть признак «сеть вернулась»
    выполнен с нулевой секунды темноты и про приёмник не говорит ничего. Второе: бывает,
    что первый LOAD приёмник всё-таки не берёт (``refuses``), и тогда показ поднимается со
    второй попытки - той, что ждала минуту.

    ⚠️ ``refuses`` - это НЕ обида на 404 и не занятый экран: наказания за 404 нет вовсе,
    ноль секунд, а LOAD после отказа берётся через 3-4 с (оба замера на живом Samsung
    Q70D, каждый повторён трижды). Заглушка моделирует то, что от приёмника остаётся после
    этих замеров: он готов быстро, но не обязан взять LOAD с первого раза.
    """

    def __init__(
        self,
        clock: _Ticker,
        warmer: _Warm,
        alive: float = 30.0,
        live: float = 180.0,
        refuses: int = 0,
        revives: int = 0,
    ) -> None:
        self.clock, self.warmer = clock, warmer
        self.live, self.refuses, self.revives = live, refuses, revives
        self.until = clock.now + alive
        self.at = 1200.0
        self.died = 0.0
        self.replays: list[float] = []
        self.when: list[float] = []
        self.revived: list[float] = []

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self, quit_app: bool = False) -> None:
        pass

    def position(self, front: float = 0.0) -> Any:
        from torrcast.cast import Position

        self.warmer.warmed += 5.0  # служба раздач жива весь показ - куски идут всегда
        if self.clock.now < self.until:
            self.at += 2.0
            return Position(self.at, 7200.0, True, "PLAYING")
        self.died = self.died or self.clock.now
        return Position(0.0, 7200.0, False, "IDLE")

    def replay(self, at: float) -> bool:
        self.replays.append(at)
        self.when.append(self.clock.now)
        if self.refuses:
            self.refuses -= 1
            return False  # 404 ещё не отпустил: LOAD приёмник не берёт
        if not self.revives:
            return False
        self.revives -= 1
        self.refuses = 1 if self.revives else 0  # следующий обрыв начнётся так же
        self.at, self.until, self.died = at, self.clock.now + self.live, 0.0
        self.revived.append(at)
        return True


def test_a_receiver_that_dropped_the_show_gets_it_back_in_seconds_not_in_a_minute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Показ бросил приёмник, источник цел - поднимаем через секунды, а не через минуту.

    Два случая тут разные, и путать их нельзя. Когда лёг ИСТОЧНИК, ждут его возврата, и
    ждать можно долго. Когда показ бросил сам ПРИЁМНИК, ждать нечего и некого, кроме него:
    замер даёт 3-4 с до готовности взять LOAD (PLAYING на 3.2-3.6 с - быстрее обычного
    тёплого LOAD), а выжидалась минута - ровно минута чёрного экрана впустую.

    Первая попытка при этом по-прежнему не стреляет в темноту нулевой длины: признак «сеть
    вернулась» тут выполнен с нулевой секунды (прогрев растёт всегда, пока жива служба
    раздач), и попытка, выстрелившая мгновенно, сгорала бы ни за чем. А осторожность никуда
    не делась - она сдвинулась на попытки со второй: не помогла самая быстрая, значит замер
    к этой аварии не подходит, и дальше снова минута (:data:`torrcast.cli.REVIVE_PAUSE`).
    """
    from torrcast import cli

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    feed.offline = ""  # упаковка на обрыв не жаловалась: рвался не источник
    warmer = _Warm()
    receiver = _Blinking(clock, warmer)

    cli._hold(receiver, feed, None, warmer, _supply(_Service()), clock=clock)  # type: ignore[arg-type]

    assert receiver.replays, "показ всё-таки поднимали - попытки не пропали вовсе"
    waited = receiver.when[0] - receiver.died
    assert waited >= cli.REVIVE_DROP, "приёмнику всё же дали те секунды, что он просит"
    assert waited < cli.REVIVE_PAUSE / 2, f"минуты чёрного экрана больше нет ({waited:.0f} с)"
    assert receiver.when[1] - receiver.when[0] >= cli.REVIVE_PAUSE, (
        "а вот вторая попытка ждёт как прежде: первая не помогла - осторожничаем"
    )
    assert len(receiver.replays) == cli.REVIVE_TRIES, "и попытки остались конечными"


def test_two_short_outages_do_not_eat_the_whole_stock_of_tries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Два коротких обрыва подряд - и оба показ переживает: запас отмерян обрыву.

    Замер на живом Q70D: за 13 минут показа два коротких обрыва израсходовали все три
    попытки, отмеренные на весь сеанс. Каждый обрыв показ пережил и человек не заметил
    ничего - но защиты на остаток вечера уже не осталось, и третий обрыв гасил бы показ
    насовсем при живых и приёмнике, и источнике.

    Возвращает запас не сам факт подъёма (это говорит приёмник), а прожитая после него
    минута настоящей картинки (:data:`torrcast.cli.REVIVE_LIVED`): мигающий показ так себе
    попытки не наотдаёт, и поток LOAD остаётся конечным.
    """
    from torrcast import cli

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    feed.offline = ""
    warmer = _Warm()
    receiver = _Blinking(clock, warmer, refuses=1, revives=2)

    cli._hold(receiver, feed, None, warmer, _supply(_Service()), clock=clock)  # type: ignore[arg-type]

    assert len(receiver.revived) == 2, "оба обрыва показ пережил, а не только первый"
    assert receiver.revived[1] > receiver.revived[0], "второй раз поднялись дальше по фильму"
    printed = capsys.readouterr().out
    assert printed.count("показ поднят с ") == 2, "и человек увидел оба подъёма"


def test_the_dark_show_is_revived_only_on_a_free_receiver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Воскрешаем только СВОЙ показ - той же аккуратностью, что и закрываем приложение.

    Пока нас не было, на том же ТВ могли начать смотреть другое: чужое приложение, чужая
    сессия в том же Default Media Receiver, чужой ``content_id`` в нашей. Перебивать такое
    нельзя ничем - ни LOAD, ни ``quit_app`` перед ним; показу остаётся честно погаснуть.
    """
    from torrcast.cast import ChromecastReceiver

    loads: list[float] = []
    monkeypatch.setattr(ChromecastReceiver, "_restart_app", lambda self: None)
    monkeypatch.setattr(ChromecastReceiver, "_load", lambda self, at=0.0: loads.append(at))
    monkeypatch.setattr(ChromecastReceiver, "_settle", lambda self, budget: True)

    aliens = [
        _FakeCast(app_id="Netflix"),
        _FakeCast(session="чужая"),
        _FakeCast(content="http://10.0.0.20:8010/cast.m3u8"),
    ]
    for alien in aliens:
        assert _receiver_on(alien).replay(1200.0) is False, "чужой показ неприкосновенен"
    assert loads == [], "в чужой показ не ушло ни одного LOAD"
    assert all(alien.log == [] for alien in aliens), "и приложение чужому не закрывали"

    for free in (_FakeCast(app_id=None), _FakeCast(app_id=ChromecastReceiver.BACKDROP_APP)):
        receiver = _receiver_on(free)
        assert receiver.replay(1200.0) is True, "экран свободен - показ поднимаем"
        assert receiver._peak == 1200.0, "сторож считает с того места, куда грузили"
    assert loads == [1200.0, 1200.0], "по одному LOAD на свободный приёмник"


def test_a_release_that_never_plays_stops_at_the_profile_not_at_eleven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Неигравший релиз: ровно столько повторов LOAD, сколько заявил профиль, - и честная
    строка вместо зависания в лестнице ожидания.

    Раньше лестница ожидания считала попытки временем бюджета, а не профилем: приёмник,
    роняющий каждый LOAD в IDLE/ERROR, получал их десяток подряд (на гейте - одиннадцать),
    всё глубже заваливаясь, а прогон висел в лестнице, пока его не прибивали руками. Теперь
    счётчик повторов LOAD один на весь показ, потолок ему - ``load_retries`` приёмника, и
    исчерпав его, показ возвращает управление честной строкой.
    """
    from torrcast.cast import ChromecastReceiver

    class _FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    clock = _FakeClock()
    monkeypatch.setattr("torrcast.cast.time.monotonic", clock.monotonic)
    monkeypatch.setattr("torrcast.cast.time.sleep", clock.sleep)

    loads: list[float] = []

    class _Silent:
        """Приёмник, берущий соединение, но роняющий каждый LOAD в IDLE/ERROR."""

        def __init__(self) -> None:
            self.app_id = ChromecastReceiver.MEDIA_APP
            self.session_id = "наша"
            self.content_id = ""
            self.player_state = "IDLE"
            self.idle_reason = "ERROR"
            self.current_time = 0.0
            self.duration = 0.0
            self.player_is_playing = False
            self.status = self
            self.media_controller = self

        def play_media(self, url: str, mime: str, current_time: float = 0.0, **_: Any) -> None:
            loads.append(current_time)

        def block_until_active(self, timeout: float = 30.0) -> None:
            pass

        def update_status(self) -> None:
            pass

        def quit_app(self, timeout: float = 10.0) -> None:
            pass

        def disconnect(self) -> None:
            pass

    receiver = ChromecastReceiver("10.0.0.50")
    receiver._cast = _Silent()
    # Чистое приложение под повтор здесь не поднимаем заново: тот же приёмник и та же
    # лента LOAD, а считаем именно её длину.
    monkeypatch.setattr(ChromecastReceiver, "_restart_app", lambda self: None)

    with pytest.raises(InfraError) as err:
        receiver.play("http://10.0.0.10:8443/index.m3u8", "кино", at=1200.0)

    assert receiver.profile.load_retries == 2, "осторожный профиль - замер Q70D"
    assert len(loads) == 1 + receiver.profile.load_retries, (
        "первый LOAD и ровно load_retries повторов - не одиннадцать по бюджету времени"
    )
    assert loads[1:] == [1200.0] * receiver.profile.load_retries, "повтор уходит туда же"
    assert "не начал показ" in str(err.value), "исчерпав попытки, показ гаснет честной строкой"


def test_the_receivers_detailed_error_survives_pychromecast_parsing() -> None:
    """Код отказа снимается с сырого ответа, пока библиотека его не выбросила."""
    from torrcast.cast import ChromecastReceiver

    seen: list[dict[str, Any]] = []

    class _Controller:
        def _process_media_status(self, data: dict[str, Any]) -> None:
            seen.append(data)

    receiver = ChromecastReceiver("10.0.0.50")
    controller = _Controller()
    receiver._catch_media_error(controller)

    controller._process_media_status(
        {"status": [{"playerState": "IDLE", "idleReason": "ERROR", "detailedErrorCode": 102}]}
    )

    assert receiver._error_code == 102, "код декодера не потерян"
    assert len(seen) == 1, "обычный разбор статуса продолжился"

    controller._process_media_status({"status": [{"playerState": "IDLE", "idleReason": "ERROR"}]})
    assert receiver._error_code is None, "отказ без кода не наследует прошлую причину"


class _Source:
    """Источник под показом на заглушке: моргает, а заглушка видит только картинку.

    Приёмник про перезапуск TorrServer не знает ничего и знать не может: у него на экране
    либо идёт картинка, либо стоит. Поэтому обрыв здесь и выглядит так же, как на ТВ, -
    декодер жив, а позиция не двигается. Возврат источника видит уже показ: раздача снова
    читается (:attr:`Feed.offline` пуст) и прогрев потащил новые куски.

    Сам декодер тут поддельный: заглушка проверяется как модель приёмника, а её ffmpeg и
    забор сегментов по сети проверяются отдельно и на настоящем ролике (см. верх файла).
    """

    def __init__(
        self,
        clock: _Ticker,
        receiver: MockReceiver,
        feed: Feed,
        warmer: _Warm,
        dur: float = 7200.0,
        dark_at: float = 10.0,
        back_at: float = 0.0,
        after: float = 6.0,
    ) -> None:
        self.clock, self.receiver, self.feed, self.warmer = clock, receiver, feed, warmer
        self.dur, self.back_at, self.after = dur, back_at, after
        self.up = True
        self.down_at = clock.now + dark_at
        self.up_at = 0.0
        self.woke = 0.0
        self.ending = 0
        #: С какой секунды заглушка пробовала открыть поток - каждый LOAD, свой и чужой.
        self.opens: list[float] = []
        clock.ticks.append(self.tick)

    def open(self, url: str, at: float = 0.0) -> None:
        """То же, что делает :meth:`MockReceiver._open`: спросить источник и завести декодер."""
        self.opens.append(at)
        if not self.up:
            raise InfraError("приёмник не забрал манифест: источника нет")
        if len(self.opens) > 1:
            self.woke = self.clock.now
        self.receiver._proc = FakeProc()  # type: ignore[assignment]
        self.receiver._start = at
        self.receiver.report.duration = self.dur
        self.receiver._pos = Position(at, self.dur, True)

    def tick(self, seconds: float) -> None:
        now = self.clock.now
        if self.up and self.down_at and now >= self.down_at:
            self.down_at, self.up_at = 0.0, (now + self.back_at if self.back_at else 0.0)
            self.up, self.feed.offline = False, "источник молчит дольше 45 с"
        elif not self.up and self.up_at and now >= self.up_at:
            self.up, self.feed.offline = True, ""  # раздача снова читается
            self.warmer.warmed += 10.0  # и прогрев потащил новые куски
        if self.woke and now - self.woke >= self.after:
            return self.finish()
        pos = self.receiver._pos
        if self.up and pos.playing:
            self.receiver._pos = Position(pos.pos + seconds, self.dur, True)

    def finish(self) -> None:
        """Показ доехал до титров, а следом кончился вход - ровно в этом порядке.

        Порядок тут и есть суть: место, с которого показ поднимают, - последнее, где он
        был живым, и у досмотренного фильма оно за порогом 95 %. Погаси декодер раньше -
        и титры сошли бы за аварию.
        """
        self.ending += 1
        if self.ending == 1:
            self.receiver._pos = Position(self.dur * 0.96, self.dur, True)
            return
        self.woke = 0.0
        self.receiver._proc.code = 0  # type: ignore[union-attr]
        self.receiver._pos = Position(self.dur * 0.96, self.dur, False)


def _blinking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patience: float = 6.0,
    **kwargs: Any,
) -> tuple[_Ticker, Feed, _Warm, MockReceiver, _Source]:
    """Показ на заглушке, под которым моргает источник - сухой прогон живой аварии.

    Терпение приёмника задаётся, а не выжидается: живьём медиасессия Samsung Q70D живёт
    23.5 с стоящей картинки, а его приложение - ещё 301 с после этого, и тест, честно
    простоявший их, никто гонять не станет. Часы у показа и у заглушки одни и свои
    (:class:`torrcast.timing.Clock`): настоящий :mod:`time` тут не трогают вовсе, потому и
    исход не зависит от того, чем занята машина.
    """
    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    warmer = _Warm(warmed=600.0)
    receiver = MockReceiver(patience=patience, clock=clock)
    source = _Source(clock, receiver, feed, warmer, **kwargs)
    monkeypatch.setattr(MockReceiver, "_open", lambda self, url, at=0.0: source.open(url, at))
    receiver.play("http://127.0.0.1:8010/index.m3u8", at=1200.0)
    return clock, feed, warmer, receiver, source


def test_a_blinking_source_takes_the_mock_receiver_dark_and_the_show_comes_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Источник моргнул - показ погас - источник вернулся - показ поднялся. На заглушке.

    Ровно этого сценария на сухом прогоне и не было: заглушка показ не бросала никогда,
    :class:`torrcast.cli._Revivable` не реализовывала, и живая авария (перезапуск
    TorrServer под показом) воскрешения не вызывала ни разу - и не могла.

    Терпение заглушки тут своё, но правила у него чужие, замеренные на живом Samsung Q70D:
    пока оно идёт, показ считается живым (``BUFFERING``) и приёмник тратит на картинку два
    своих перезабора куска по HTTP (повторами LOAD они не были никогда - сессия та же);
    кончилось - сессии нет, и позиция в ней читается нулём.
    """
    from torrcast import cli

    clock, feed, warmer, receiver, source = _blinking(tmp_path, monkeypatch, back_at=120.0)

    cli._hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    first, own, revival = source.opens[0], source.opens[1:3], source.opens[3:]
    assert first == 1200.0, "показ начался с 20-й минуты"
    assert own == [1208.0, 1208.0], "приёмник потратил на пропавшую картинку свои два LOAD"
    assert revival == [1208.0], "воскрешение пришло снаружи - и ровно с места остановки"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:08" in printed, "заглушка бросила показ, а не досидела до конца"
    assert "сеть вернулась - поднимаю показ с 0:20:08" in printed
    assert "показ поднят с 0:20:08" in printed, "картинка вернулась, и заглушка это подтвердила"


def test_the_mock_receiver_burns_its_patience_before_it_drops_the_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Терпение заглушки - не бутафория: пока оно идёт, показ живой и воскрешать нечего.

    Живой приёмник на стоящей картинке уходит в ``BUFFERING`` и держится примерно четыре
    минуты. Заглушка, гаснущая на первом же неподвижном опросе, звала бы воскрешение там,
    где настоящий ТВ ещё показывает фильм, - то есть врала бы в другую сторону.
    """
    clock, _, _, receiver, source = _blinking(tmp_path, monkeypatch, dark_at=0.0)

    # ⚠️ Числа переписаны по замеру 09-08-2026 (живой Q70D, рапорт приёмника + tcpdump):
    # прежние «240 с» склеивали два РАЗНЫХ срока - смерть медиасессии (23.5 с) и уход
    # приложения с экрана (301 с), - а «повторы LOAD» на деле оказались перезаборами
    # куска по HTTP: media_session_id при них не менялся. Поведение теста не изменилось:
    # терпение он и раньше задавал сам, а проверяет он правила, а не цифры.
    assert MockReceiver.PATIENCE == 23.5, "замер: столько живёт медиасессия после стопа"
    assert MockReceiver.SEGMENT_RETRIES == 2, "и ровно два перезабора куска внутри неё"

    seen = []
    for _ in range(6):
        clock.sleep(2.0)  # опрос показа раз в 2 с, как в жизни
        seen.append(receiver.position())

    states = [(round(p.pos), p.playing, p.state) for p in seen]
    assert states[0] == (1200, True, "PLAYING"), "первый опрос - картинка ещё шла"
    assert states[1:4] == [(1200, True, "BUFFERING")] * 3, "картинка стоит, но показ живой"
    assert states[4:] == [(0, False, "IDLE")] * 2, "терпение вышло - сессии нет, позиции тоже"
    assert source.opens == [1200.0, 1200.0, 1200.0], "свои повторы потрачены внутри терпения"
    assert clock.now - 1000.0 == 12.0, "и всё это - заданное терпение, а не выжданные минуты"


def test_a_source_that_never_returns_ends_the_show_on_the_mock_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Источник не вернулся - гаснем честно: попытки конечны, LOAD в приёмник не летит.

    Отрицательная половина того же сценария. Заглушка обязана уметь и её: показ, который
    поднимается на сухом прогоне всегда, доказывал бы ровно ничего.
    """
    from torrcast import cli

    clock, feed, warmer, receiver, source = _blinking(tmp_path, monkeypatch)

    cli._hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert source.opens == [1200.0, 1208.0, 1208.0], "после своих двух повторов - ни одного LOAD"
    assert clock.now - 1000.0 > cli.REVIVE_LIMIT, "ждали ровно столько, сколько обещали"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:08" in printed
    assert "показ поднять не удалось" in printed and "cast продолжит с 0:20:08" in printed


def test_the_mock_receiver_takes_a_load_right_after_a_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """404 заглушка наказывает ровно столько, сколько сказано в профиле, - то есть нисколько.

    🔴 Ожидание переписано по замеру 09-08-2026 (живой Q70D, рапорт приёмника + tcpdump):
    наказание за 404 опровергнуто трижды - LOAD после него берётся даже быстрее обычного
    тёплого. Прежний тест закреплял ровно ту легенду, которую замер снял, и оставить его
    значило бы держать в сухом прогоне выдуманную аварию.

    Что от него осталось и почему: сам механизм наказания жив и берётся из профиля
    (:attr:`torrcast.profile.Profile.sulk`) - мерили чистый 404 в здоровой сессии, и
    приёмник, который всё-таки обижается, должен настраиваться числом, а не правкой кода.
    На решение «держать запрос вместо 404» этот ноль не влияет: там своя причина.
    """
    clock = _Ticker()
    opens: list[float] = []
    receiver = MockReceiver(clock=clock)
    receiver._url = "http://127.0.0.1:8010/index.m3u8"
    monkeypatch.setattr(MockReceiver, "_open", lambda self, url, at=0.0: opens.append(at))

    receiver._caught(_Answer(404))
    assert MockReceiver.SULK == 0.0, "наказания за 404 нет - замер снял его трижды"
    assert receiver.replay(1200.0) is False, "картинки нет - врать о поднятом показе нельзя"
    assert opens == [1200.0], "но попытку приёмник принял сразу, не выжидая ни секунды"

    # Что наказание всё ещё СТАВИТСЯ числом профиля - проверяется отдельно
    # (tests/test_profile.py): механизм жив, изменилась только замеренная величина.


class _Answer:
    """Ответ раздачи глазами приёмника - от него нужен только код."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_the_show_directory_is_left_clean_after_the_stop(tmp_path: Path) -> None:
    """После остановки в каталоге показа не остаётся ничего — включая флажок картинки
    и каталог прогона упаковки.

    `cast stop` оставлял в /dev/shm/torrcast пустой playing.flag: сегменты и плейлист
    убирались, а доказательство прошлой картинки — нет. Каталог прогона (:data:`PACK_DIR`)
    сюда добавился вместе с публикацией через переименование: в нём остаётся недописанный
    кусок и список нарезанного, и в tmpfs им после показа делать нечего.
    """
    feed = _feed_with_segments(tmp_path)
    (feed.out / PACK_DIR).mkdir(exist_ok=True)
    (feed.out / PACK_DIR / "v61.ts").write_text("недописанный кусок")
    mark_playing(feed.out)

    feed.stop()

    assert list(feed.out.iterdir()) == [], "каталог показа пуст, мусора не осталось"


def test_a_repack_in_the_middle_keeps_the_proof_of_the_picture(tmp_path: Path) -> None:
    """Флажок снимается в конце показа, а не в середине.

    Перемотка и обрыв упаковки перезапускают ffmpeg (:meth:`Feed.restart`), но показ при
    этом тот же самый и картинка на экране никуда не делась — CLI своё «старт NN с» уже
    сказал. Снимать доказательство на каждом перезапуске значило бы врать.
    """
    feed = _feed_with_segments(tmp_path)
    mark_playing(feed.out)
    assert feed.packer is not None

    feed.packer.stop(keep_files=True)  # так гаснет упаковка между кусками фильма

    assert playing_flag(feed.out).exists(), "показ идёт - флажок на месте"
    assert sorted(feed.out.glob("v*.ts")), "упакованное перезапуск не выбрасывает"


def test_a_finished_packer_is_not_a_crash_but_a_serial_one_gives_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Конец входа и обрыв — разные вещи, и показ обязан их различать.

    Код 0 — фильм упакован до конца, падать не с чего. Обрыв — повод начать заново с того
    места, где стоит приёмник; но если рвётся раз за разом, показ сдаётся честной строкой,
    а не крутит круг вечно.

    ⚠️ «Раз за разом» — это про ПРОГОНЫ, а не про опросы: каждый перезапуск даёт новый
    процесс, и наказывать за обрыв надо его, а не считать заново тот же труп на каждом
    запросе сегмента (их приходит по пять в секунду).
    """
    feed = _feed_with_segments(tmp_path)
    assert feed.packer is not None

    def again(self: Feed, slot: int) -> None:  # перезапуск = новый процесс упаковки
        self.packer = fake_packer(self.out, first=0, code=-9)

    feed.packer.proc.code = 0  # type: ignore[attr-defined]
    assert feed.segment(70) is None and feed.trouble() == "", "дошли до конца фильма"

    feed.packer.proc.code = -9  # type: ignore[attr-defined]
    monkeypatch.setattr(Feed, "restart", again)
    for _ in range(feed.limit):
        feed.restarted = 0.0  # прогоны идут не подряд: защита «не толкаемся» тут не при чём
        feed.segment(70)
    assert feed.trouble() == "", "обрыв переживаем молча, пока попытки не кончились"

    feed.restarted = 0.0
    feed.segment(70)
    assert feed.trouble() == "убит сигналом 9"


def test_one_dead_run_is_blamed_once_and_not_on_every_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Один труп упаковки не съедает все попытки за полсекунды.

    Живой сценарий: TorrServer выронил раздачу посреди показа, вход мёртв, ffmpeg умирает
    сразу после старта — то есть внутри двух секунд, пока держит защита «не толкаемся».
    Пока обрыв считался на каждый запрос сегмента, три попытки сгорали за 0.8 с и показ
    умирал, ни разу по-настоящему не перезапустив упаковку.
    """
    feed = _feed_with_segments(tmp_path)
    assert feed.packer is not None
    monkeypatch.setattr(Feed, "restart", lambda self, slot: None)

    feed.packer.proc.code = -9  # type: ignore[attr-defined]
    feed.restarted = time.monotonic()  # перезапуск только что был - второй не нужен
    for _ in range(10):
        feed.segment(70)

    assert (feed.crashes, feed.trouble()) == (1, ""), "труп наказан один раз, показ жив"


def test_resume_starts_from_the_offset_and_ends_as_watched(
    clip: str, tls: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    """Тот же показ, но с середины: ffmpeg стартует с `-ss`, приёмник декодирует остаток,
    сторож кладёт в state абсолютную позицию, а на 95 % пишет «досмотрено».
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    # Длительность занижена на сегмент - хвост HLS у клиента может отвалиться, а проверяем
    # мы тут переход «досмотрено», а не хвост. Сетку показа считаем той же арифметикой,
    # что и он сам: позиция берётся на границе, иначе упаковка законно начнётся с начала
    # сегмента и проверять было бы нечего.
    length = float(CLIP_SECONDS - HLS_SEGMENT_SECONDS)
    offset = Grid.uniform(length).start(1)
    key = "movie:ролик:2026"
    entry = Entry(title="ролик", magnet="magnet:?xt=1", pos=offset, dur=length)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    config = config_for(tmp_path, tls)
    assert _play(config, clip, 0, "тест", _Clock(), watch=watch) == 0

    printed = capsys.readouterr().out
    decoded = float(printed.split("декодировано ")[1].split(" ")[0])
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "показ оборвался"
    assert f"упаковка с {offset:.1f} с" in printed, "показ начался с позиции, а не сначала"
    assert "досмотрено" in printed
    saved = State.load().get(key)
    assert saved is not None and saved.done and saved.pos == 0.0


class _FakeController:
    def __init__(self, jumps: list[float]) -> None:
        self.jumps = jumps

    def seek(self, pos: float) -> None:
        self.jumps.append(pos)


class _FakeDevice:
    def __init__(self, jumps: list[float]) -> None:
        self.media_controller = _FakeController(jumps)


def test_a_stuck_receiver_is_nudged_only_when_the_packing_is_ahead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Неподвижный BUFFERING — это две разные беды, и лечатся они по-разному.

    Замерено на живом Q70D: на 1:24 фильма приёмник встал намертво при 60 с
    готовой упаковки впереди, сам не ожил ни разу и оживал только от нашего ``seek``. А
    ровно так же выглядит приёмник, который честно ждёт упаковку, — и вот его трогать
    нельзя: прыжок уведёт показ в неупакованное место и заставит паковать заново.
    """
    from torrcast.cast import ChromecastReceiver

    jumps: list[float] = []
    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice(jumps))
    receiver = ChromecastReceiver("10.0.0.50")
    receiver._peak = 84.0

    receiver._nudge(84.0, front=144.0)
    assert jumps == [], "первый неподвижный тик - ещё не зависание"

    receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
    receiver._nudge(84.0, front=88.0)
    assert jumps == [], "запаса впереди нет - приёмник ждёт нас, а не завис"

    receiver._nudge(84.0, front=144.0)
    assert jumps == [84.0 + ChromecastReceiver.STALL_SKIP], "еда на столе - расшевелить"


#: Сетка «Моаны» 2016 вокруг места, на котором показ умер: границы взяты у неё же.
_MOANA = Grid((0.0, 112.905, 124.583, 137.095, 148.940, 161.037), 6500.285, True)


def test_a_nudge_lands_past_the_segment_and_not_eight_seconds_ahead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Прыжок мимо застрявшего куска обязан быть длиннее самого куска.

    Замер на «Моане» 2016: показ встал на 127.2 с внутри сегмента
    ``[124.583..137.095)``, а сторож прыгнул на 8 с — то есть в тот же сегмент, откуда
    и прыгал. Оба нуджа сеанса приземлились туда же, и застрявший кусок так и остался
    впереди: 5 мин 48 с показа сдвинули картинку на 2.4 с.
    """
    from torrcast.cast import ChromecastReceiver

    jumps: list[float] = []
    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice(jumps))
    receiver = ChromecastReceiver("10.0.0.50")
    receiver.next_cut = _MOANA.after
    receiver._peak = 127.2

    assert _MOANA.slot_at(127.2 + ChromecastReceiver.STALL_SKIP) == _MOANA.slot_at(127.2), (
        "замер: прежний шаг не выводил из сегмента вовсе"
    )

    receiver._nudge(127.2, front=200.0)
    receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
    receiver._nudge(127.2, front=200.0)

    assert jumps == [137.095 + ChromecastReceiver.CUT_SLACK]
    assert _MOANA.slot_at(jumps[0]) == _MOANA.slot_at(127.2) + 1, "прыгнули ровно на кусок вперёд"


def test_a_segment_that_keeps_killing_the_show_is_stepped_over(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Показ, умирающий на одном куске, обязан однажды перешагнуть его, а не ходить кругом.

    Замер на «Моане» 2016: четыре смерти, три воскрешения и семь повторов LOAD подряд —
    и каждый круг возвращал приёмник на то же место, получая тот же исход, до самого
    конца сеанса. Первые смерти при этом законны: моргнувшую сеть от невоспроизводимого
    куска отличает только счёт.
    """
    from torrcast.cast import ChromecastReceiver

    loads: list[float] = []
    monkeypatch.setattr(ChromecastReceiver, "_restart_app", lambda self: None)
    monkeypatch.setattr(ChromecastReceiver, "_load", lambda self, at=0.0: loads.append(at))
    monkeypatch.setattr(ChromecastReceiver, "_free", lambda self: True)
    monkeypatch.setattr(ChromecastReceiver, "_settle", lambda self, budget: True)
    receiver = ChromecastReceiver("10.0.0.50")
    receiver.next_cut = _MOANA.after
    receiver._peak = 127.2

    assert receiver._reload() is True
    assert receiver._reload() is True
    assert loads == [127.2, 127.2], "первые смерти возвращают человека туда, где он смотрел"

    assert receiver.replay(127.2) is True
    assert loads[-1] == 137.095 + ChromecastReceiver.CUT_SLACK, "третья смерть - кусок перешагнут"
    assert "перешагиваю" in capsys.readouterr().out, "решение сказано вслух"


class _Reported:
    """MEDIA_STATUS, как его отдаёт живой приёмник: позиция, состояние, длительность."""

    def __init__(self, pos: float, state: str = "PLAYING") -> None:
        self.current_time = pos
        self.player_state = state
        self.idle_reason = None
        self.duration = 5977.0
        self.player_is_playing = state in {"PLAYING", "BUFFERING"}


def test_the_peak_follows_the_viewer_back_after_a_rewind(monkeypatch: pytest.MonkeyPatch) -> None:
    """После перемотки назад нудж обязан целиться туда, где человек СЕЙЧАС.

    Замерено на живом Q70D дважды подряд: откат с 31:31 на 10:00, показ шёл
    чисто 18 с, потом ребуфер — и сторож выкинул фильм обратно на 31:31, в место, откуда
    зритель только что ушёл. Причина — пройденный максимум ``_peak``, который никогда не
    опускался: прыгаем мы только вперёд, поэтому уехавшая назад позиция может значить
    ровно одно — перемотку человека, и максимум обязан пойти за ним.
    """
    from torrcast.cast import ChromecastReceiver

    jumps: list[float] = []
    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice(jumps))
    receiver = ChromecastReceiver("10.0.0.50")
    monkeypatch.setattr(ChromecastReceiver, "_status", lambda self: self.script.pop(0))
    stall = [_Reported(619.0, "BUFFERING")] * 2
    receiver.script = [_Reported(1891.0), _Reported(600.0), *stall]  # type: ignore[attr-defined]

    receiver.position(front=1951.0)  # шли на 31:31
    receiver.position(front=600.0)  # пульт: откат на 10:00
    assert receiver._peak == 600.0, "максимум пошёл за человеком, а не остался на 31:31"

    receiver.position(front=688.0)  # встали на 10:19 при готовой упаковке впереди
    receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
    receiver.position(front=688.0)

    assert jumps == [619.0 + ChromecastReceiver.STALL_SKIP], (
        "нудж целится на кусок вперёд от текущего места, а не назад в покинутое"
    )


class _Gone:
    """Ушедший приёмник: ``seek`` принимает, указатель двигает - а кадра не даёт ни разу.

    Ровно так выглядит замер: приёмник послушно отвечает на каждый нудж новой позицией и
    остаётся в ``BUFFERING``, поэтому «указатель поехал» доказательством вылеченного
    подвиса быть не может.
    """

    def __init__(self, pos: float = 84.0) -> None:
        self.status = _Reported(pos, "BUFFERING")
        self.media_controller = self
        self.jumps: list[float] = []

    def seek(self, pos: float) -> None:
        self.jumps.append(pos)
        self.status = _Reported(pos, "BUFFERING")

    def freeze(self) -> None:
        self.status = _Reported(self.status.current_time, "BUFFERING")

    def show(self, pos: float) -> None:
        self.status = _Reported(pos, "PLAYING")


def _watched(monkeypatch: pytest.MonkeyPatch, gone: _Gone) -> Any:
    from torrcast.cast import ChromecastReceiver

    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: gone)
    monkeypatch.setattr(ChromecastReceiver, "_status", lambda self: gone.status)
    return ChromecastReceiver("10.0.0.50")


def test_a_blind_ladder_of_nudges_gives_up_instead_of_walking_the_movie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Лестница нуджей без единого показанного кадра обязана кончиться - и передать
    показ воскрешению.

    Замер: за 780 с показа сторож сработал 24 раза, и 12 из них были одной лестницей
    подряд, без единого ``PLAYING`` между прыжками. Это не залипший кусок, а ушедший
    приёмник: прыжки его не лечат, а только шагают по фильму - те 12 нуджей увели
    указатель на 96 с впустую, и каждый стоил 8 с неподвижной картинки и до 8 с плёнки.
    """
    from torrcast.cast import ChromecastReceiver

    gone = _Gone(84.0)
    receiver = _watched(monkeypatch, gone)

    result = receiver.position(front=1e6)
    for _ in range(30):  # минута показа при опросе раз в 2 с
        receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
        result = receiver.position(front=1e6)
        if not result.playing:
            break

    limit = ChromecastReceiver.BLIND_NUDGES
    assert len(gone.jumps) == limit, "лестница не остановилась - сторож шагает по фильму"
    assert gone.jumps == [84.0 + 8.0 * step for step in range(1, limit + 1)]
    assert not result.playing, "показ живым больше не считается - эстафета воскрешению"
    assert result.state == "BUFFERING", "состояние приёмника отдаём как есть, без вранья"
    assert gone.jumps[-1] - 84.0 == 8.0 * limit, "по фильму прошагано ровно на лестницу"


def test_a_single_nudge_still_pulls_the_receiver_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """Штатный случай - подвис, вылеченный ОДНИМ нуджем, - счётчик лестницы не трогает.

    Пять разных подвисов за показ, каждый вылечен одним прыжком: показ всё это время
    живой, сторож всё это время на месте. Обнуляет счёт именно показанный кадр.
    """
    from torrcast.cast import ChromecastReceiver

    gone = _Gone(84.0)
    receiver = _watched(monkeypatch, gone)

    for _ in range(5):
        gone.freeze()
        receiver.position(front=1e6)  # первый неподвижный тик - ещё не зависание
        receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
        assert receiver.position(front=1e6).playing, "одиночный нудж показ не хоронит"
        gone.show(gone.status.current_time + 2.0)  # прыжок помог: кадр на экране
        assert receiver.position(front=1e6).state == "PLAYING"

    assert len(gone.jumps) == 5, "сторож остался на месте - лечить подвисы больше некому"
    assert receiver._blind == 0 and not receiver._gone


def test_only_the_cosmetic_pychromecast_line_is_hushed(caplog: pytest.LogCaptureFixture) -> None:
    """Гасим РОВНО одну строку чужой библиотеки, а настоящие её жалобы доходят.

    Строка про «не смог определить тип устройства» печатается на каждом подключении и
    ничего не значит: pychromecast спрашивает страницу сведений по https на 8443,
    которого у телевизора нет, ловит отказ тут же и подставляет тип по умолчанию.
    ``port=8009`` в её тексте - распечатка списка сервисов, а не отказавший порт; на этом
    уже строилась ложная гипотеза «телевизор выпадает по 8009».
    """
    from torrcast import cast

    cast.hush_cosmetic_noise()
    cast.hush_cosmetic_noise()  # второй вызов второго фильтра не вешает
    logger = logging.getLogger("pychromecast.dial")
    assert len(logger.filters) == 1

    with caplog.at_level(logging.WARNING, logger="pychromecast.dial"):
        logger.warning(
            "Failed to determine cast type for host %s (%s) (services:%s)",
            "10.0.0.50",
            "[Errno 111] Connection refused",
            "[HostServiceInfo(host='10.0.0.50', port=8009)]",
        )
        logger.error("Failed to connect to service %s, retrying in %.1fs", "тв", 5.0)

    said = [record.getMessage() for record in caplog.records]
    assert len(said) == 1, "приглушать надо одну строку, а не логгер целиком"
    assert said[0].startswith("Failed to connect"), "настоящая ошибка обязана доходить"


class _FakeStatus:
    """Статус приёмника, как его отдаёт кэш pychromecast: приложение и его сессия."""

    def __init__(self, app_id: str | None, session_id: str = "наша", content: str = "") -> None:
        self.app_id = app_id
        self.session_id = session_id
        self.content_id = content


class _FakeCast:
    """Приёмник, записывающий, что с ним сделали: показ, приложение, соединение."""

    def __init__(
        self, app_id: str | None = "CC1AD845", session: str = "наша", content: str = ""
    ) -> None:
        self.status = _FakeStatus(app_id, session, content)
        self.media_controller = _FakeMedia(self)
        self.log: list[str] = []

    def quit_app(self, timeout: float = 10.0) -> None:
        self.log.append("quit")

    def disconnect(self) -> None:
        self.log.append("disconnect")


class _FakeMedia:
    def __init__(self, cast: _FakeCast) -> None:
        self.status = cast.status
        self._cast = cast

    def stop(self) -> None:
        self._cast.log.append("stop")


def _receiver_on(cast: _FakeCast, url: str = "http://10.0.0.10:8443/index.m3u8") -> Any:
    from torrcast.cast import ChromecastReceiver

    receiver = ChromecastReceiver("10.0.0.50")
    receiver._cast, receiver._url, receiver._session = cast, url, "наша"
    return receiver


def test_the_receiver_app_is_closed_only_on_our_own_session() -> None:
    """Иконку Default Media Receiver после показа снимаем — но только свою.

    Иначе после `cast stop` и после титров приёмник висит на экране до своего таймаута
    простоя и мешает ТВ уснуть. Лечится это ``quit_app``. Опасность ровно одна: на том же
    Q70D кастят и другие приложения, а приложение-приёмник у них то же самое
    (``CC1AD845``) — чужой показ снимать нельзя ни при каких обстоятельствах.
    """
    ours = _FakeCast(content="http://10.0.0.10:8443/index.m3u8")
    _receiver_on(ours).stop(quit_app=True)
    assert ours.log == ["stop", "quit", "disconnect"], (
        "своя сессия: гасим показ, закрываем приложение, отпускаем сокет"
    )

    between = _FakeCast(content="http://10.0.0.10:8443/index.m3u8")
    _receiver_on(between).stop()
    assert between.log == ["stop"], "стык серий: приложение остаётся под следующую серию"

    alien_app = _FakeCast(app_id="Netflix")
    _receiver_on(alien_app).stop(quit_app=True)
    assert alien_app.log == [], "на ТВ чужое приложение - не наше дело"

    closed = _FakeCast(app_id=None)
    _receiver_on(closed).stop(quit_app=True)
    assert closed.log == [], "приёмник уже закрыт - закрывать нечего"

    alien_session = _FakeCast(session="чужая")
    _receiver_on(alien_session).stop(quit_app=True)
    assert alien_session.log == [], "то же приложение, но сессию поднял не мы"

    alien_media = _FakeCast(content="http://10.0.0.20:8010/cast.m3u8")
    _receiver_on(alien_media).stop(quit_app=True)
    assert alien_media.log == [], "в то же приложение загрузился чужой сендер"


def test_the_show_end_closes_the_app_and_the_episode_seam_does_not(
    clip: str, tls: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стык серий и конец показа — для приёмника разные события.

    Проверяется вся проводка целиком, от состояния до приёмника: сторож дошёл до порога
    95 %, показ кончился — и только запись состояния решает, закрывать ли приложение.
    Серия не последняя — оно достаётся следующей; последняя — гаснет, как у фильма.
    """
    from torrcast import cli
    from torrcast.cast import MockReceiver

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    quits: list[bool] = []

    class _Recorder(MockReceiver):
        def stop(self, quit_app: bool = False) -> None:
            quits.append(quit_app)
            super().stop()

    monkeypatch.setattr(
        cli, "make_receiver", lambda kind, address="", ca="", profile=None: _Recorder()
    )
    config = config_for(tmp_path, tls)
    key = "tv:сериал:2026"
    length = float(CLIP_SECONDS)

    def run(episode: int) -> None:
        entry = Entry(
            title="сериал", magnet="magnet:?xt=1", kind="tv", season=1, episode=episode,
            episodes=[[1, 1, 0], [1, 2, 1]], pos=length, dur=length,
        )  # fmt: skip
        state = State()
        state.put(key, entry)
        state.save()
        _play(config, clip, 0, "тест", _Clock(), watch=_Watch(key=key, entry=entry, every=0.0))

    run(episode=1)
    assert quits == [False], "серия досмотрена, впереди s1e2 - приложение не трогаем"

    run(episode=2)
    assert quits == [False, True], "последняя серия - показ окончен, приложение закрываем"


def test_a_finished_movie_hands_nothing_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Конец фильма (титры) и `cast stop` посреди — оба раза передавать показ некому,
    значит приложение приёмника закрывается.
    """
    from torrcast import cli

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    key = "movie:ролик:2026"
    entry = Entry(title="ролик", magnet="magnet:?xt=1", pos=95.0, dur=100.0)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    assert not cli._handover(watch), "`cast stop`: сторож не досматривал - передавать нечего"

    watch.flush()  # порог 95 %: фильму это «досмотрено», а не следующая серия
    assert watch.done and not cli._handover(watch), "титры кончились - закрываем приложение"


def test_a_closed_show_never_starts_ffmpeg_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Показ окончен — поток раздачи, проснувшийся в segment(), не поднимает упаковку.

    На стыке серий следующая серия уже чистит каталог и пакует своё; осиротевший ffmpeg
    прошлой серии выкладывал бы туда её сегменты под теми же именами.
    """
    asked: list[int] = []
    feed = _feed_with_segments(tmp_path)
    monkeypatch.setattr(Feed, "restart", lambda self, slot: asked.append(slot))

    feed.stop()

    assert feed.segment(70) is None and asked == [], "после stop упаковку не поднимаем"


def test_a_planned_stop_of_the_show_is_a_success_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`cast stop` обязан оставлять юнит кодом 0.

    SIGTERM от `cast stop` поднимает исключение — иначе показ не пройдёт через ``finally``
    и не запишет позицию. Но исключение это штатное, и выходить на нём кодом 2 нельзя:
    systemd помечает юнит ``failed``, и после каждой нормальной остановки пользователь видит
    красную строку в статусе. Ctrl-C на вопросе отказом при этом быть не перестаёт.
    """
    from torrcast import cli

    caught: list[BaseException] = []

    def terminated() -> int:
        try:
            cli._on_term(15, None)
        except BaseException as exc:  # ловим ровно затем, чтобы посмотреть на него
            caught.append(exc)
            raise
        return cli.EXIT_OK

    monkeypatch.setattr(cli, "_cmd_status", terminated)
    assert cli.main(["status"]) == cli.EXIT_OK, "`cast stop` - это успех показа, а не отказ"
    assert isinstance(caught[0], KeyboardInterrupt), "раскрутка обязана идти как прежде"

    monkeypatch.setattr(cli, "_cmd_status", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert cli.main(["status"]) == cli.EXIT_INFRA, "Ctrl-C остаётся отказом"


def test_the_cli_never_kills_a_show_that_is_still_inside_the_units_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ожидание картинки согласовано с бюджетами юнита, а не взято «побольше».

    CLI ждёт картинку и по своему таймауту гасит показ. Пока он ждал 120 с, а юнит имел
    право потратить на метаданные, ffprobe, карту, пробный прогон и терпение к молчащему
    приёмнику куда больше, `cast` убивал показ, который вот-вот начался бы. Согласие
    здесь одно: ждать не меньше суммы потолков всех фаз, которые юнит проходит до
    первого ``PLAYING``.
    """
    from torrcast import cli
    from torrcast.cast import ChromecastReceiver
    from torrcast.stream import KEYS_WAIT, PILOT_TIMEOUT

    phases = (
        cli.WORKER_META  # метаданные раздачи по DHT
        + cli.WORKER_DUR  # ffprobe длительности серии
        + KEYS_WAIT  # чужая карта опорных кадров снимается прямо сейчас
        + PILOT_TIMEOUT  # пробный прогон упаковки в один кадр
        + ChromecastReceiver.START_TIMEOUT  # молчаливый IDLE после LOAD
    )
    assert phases <= cli.START_BUDGET, "CLI сдаётся раньше, чем юнит исчерпал своё право"

    now, stopped = [0.0], []
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    monkeypatch.setattr(cli, "unit_active", lambda: True)
    monkeypatch.setattr(cli, "unit_why", lambda: "юнит ещё идёт к картинке")
    monkeypatch.setattr(cli, "stop_play_unit", lambda: stopped.append(now[0]))

    class _Mute:
        def phase(self, text: str) -> None: ...

    with pytest.raises(InfraError):
        cli._await_playing(Config(hls_dir=str(tmp_path)), _Mute())  # type: ignore[arg-type]

    assert stopped and stopped[0] >= phases, "показ погашен внутри бюджета юнита"


class _Service:
    """Служба раздач глазами показа: жива ли, что у неё в списке и что она знает о файлах.

    Ровно те три вопроса, из которых складывается ответ «виноват источник»
    (:meth:`torrcast.stream.Supply.check`), плюс счётчик добавлений: возврат раздачи
    магнитом обязан быть идемпотентным и не трогать ничего, кроме нашего хэша.
    """

    def __init__(self, up: bool = True, listed: bool = True, files: bool = True) -> None:
        self.up, self._listed, self._files = up, listed, files
        self.added: list[str] = []
        self.dropped: list[str] = []

    def alive(self) -> bool:
        return self.up

    def listed(self, torrent_hash: str) -> bool:
        if not self.up:
            raise InfraError("TorrServer не отвечает")
        return self._listed

    def files(self, torrent_hash: str) -> list[object]:
        if not self.up:
            raise InfraError("TorrServer не отвечает")
        return [object()] if self._files else []

    def add(self, magnet: str) -> str:
        if not self.up:
            raise InfraError("TorrServer не отвечает")
        self.added.append(magnet)
        # Магнит вернул раздаче трекеры: она снова в списке и снова с метаданными.
        self._listed = self._files = True
        return MAGNET_HASH

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)

        return True


MAGNET_HASH: Final = "9a76e7bc1701cf0eb3efe4d9518c999b6ee8a8e4"
MAGNET: Final = f"magnet:?xt=urn:btih:{MAGNET_HASH}&tr=udp%3A%2F%2Ftracker.example%3A1337"


def _supply(service: _Service) -> Any:
    from torrcast.stream import Supply

    return Supply(service, torrent_hash=MAGNET_HASH, magnet=MAGNET)  # type: ignore[arg-type]


def _events(directory: Path) -> list[dict[str, Any]]:
    from torrcast import trace

    trace.shutdown()
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("trace-*.jsonl")):
        for raw in path.read_text("utf-8").splitlines():
            rows.append(json.loads(raw))
    return rows


def test_a_dead_source_is_named_instead_of_blaming_the_receiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Показ гаснет при мёртвом источнике - и виноватым называется ИСТОЧНИК.

    Замер на живом стенде: перезапуск службы раздач посреди показа кончал показ за
    3.5-12 с, человек 14 с не видел ни строки, а потом получал «приёмник не досмотрел
    поток». Своих признаков у показа тут нет ни одного: трёхсекундный обрыв не взводит
    ни счёт оборванных прогонов, ни часы молчания, и :attr:`Feed.offline` пуст. Поэтому
    прежде, чем признать показ погасшим, спрашивается сам источник - и его ответ уходит
    одной и той же строкой и человеку, и в недельный след.
    """
    from torrcast import cli, trace

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path / "trace"))
    (tmp_path / "trace").mkdir()
    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    service = _Service(up=False)

    cli._hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00 (TorrServer не отвечает)" in printed, (
        "человеку сказано про источник, а не про приёмник"
    )
    rows = _events(tmp_path / "trace")
    dark = next(r for r in rows if r["event"] == "dark")
    offline = next(r for r in rows if r["event"] == "offline")
    assert dark["why"] == "TorrServer не отвечает" == offline["why"], "след и строка совпадают"
    assert offline["asked"] is True, "причина взята у самого источника, а не угадана"
    assert receiver.replays == [], "пока источник лежит, терпение приёмника не жжём"


def test_the_returning_source_gets_the_torrent_back_by_magnet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Служба вернулась - раздачу добавляем МАГНИТОМ, и только потом поднимаем показ.

    После перезапуска списка раздач у службы нет вовсе (заводим их с ``save_to_db:false``),
    а в URL потока едет только хэш: попросив по нему поток, мы получили бы раздачу без
    трекеров - замерено, 25 с и ноль байт, пиры только по DHT. Трекеры живут в магните из
    записи картины, и возвращает их этот вызов - ровно один, идемпотентный и только по
    нашему хэшу.
    """
    from torrcast import cli, trace

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path / "trace"))
    (tmp_path / "trace").mkdir()
    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    warmer.warmed = 0.0  # прогрева нет: возврат показа держится только на источнике
    service = _Service(up=False)

    def restore(_seconds: float) -> None:
        service.up = clock.now - 1000.0 >= 30.0
        if service.up:
            (feed.out / segment_name(feed.grid.slot_at(1200.0))).write_bytes(b"ready")

    clock.ticks.append(restore)
    service._listed = service._files = False  # перезапуск: своей раздачи она не помнит

    cli._hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    assert service.added == [MAGNET], "раздачу вернули магнитом ровно один раз"
    assert service.dropped == [], "чужих раздач и своей же не сносим - только добавляем"
    assert receiver.replays == [1200.0], "показ поднят с того места, где смотрели"
    printed = capsys.readouterr().out
    assert "источник вернулся - раздачу добавил магнитом заново" in printed
    rows = _events(tmp_path / "trace")
    back = next(r for r in rows if r["event"] == "resupply")
    assert back["torrent"] == MAGNET_HASH and back["ok"] is True


def test_a_torrent_left_as_a_bare_hash_is_a_source_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Раздача есть, а метаданных нет - это раздача, заведённая по голому хэшу.

    Так она и появляется: наш же URL потока просит службу о хэше, та заводит раздачу без
    единого трекера и ищет пиров одним DHT. Считать источник исправным в этот момент -
    то же самое, что молчать: показ не получит ни байта.
    """
    service = _Service(up=True, listed=True, files=False)
    supply = _supply(service)

    why = supply.check()

    assert why == "" and supply.restored, "раздачу без трекеров вернули магнитом сразу же"
    assert service.added == [MAGNET]
    assert supply.check() == "" and service.added == [MAGNET], "второй раз добавлять нечего"


def test_a_healthy_source_is_never_blamed_and_never_re_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Источник в порядке - он и молчит: ни строки обвинения, ни лишнего добавления."""
    service = _Service()
    supply = _supply(service)

    assert supply.check() == "" and not supply.restored
    assert service.added == [] and service.dropped == []


def test_a_dead_source_does_not_kill_the_show_when_packing_gives_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Упаковка сдалась, а виноват источник - показ не умирает, а ждёт его возврата.

    Три оборванных подряд прогона значат «показывать нечего» только при живом источнике.
    Служба раздач, которую перезапустили, рвёт вход точно так же, и старый показ хоронил
    себя строкой «упаковка оборвалась» - про наш ffmpeg, а не про причину.
    """
    from torrcast import cli, trace

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path / "trace"))
    (tmp_path / "trace").mkdir()
    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    feed.fatal = "ffmpeg сдался: Input/output error"
    service = _Service(up=False)

    cli._hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    printed = capsys.readouterr().out
    assert "источник не читается (TorrServer не отвечает) - жду его возврата" in printed
    assert "упаковка оборвалась" not in printed, "показ не хоронит себя чужой виной"
    assert feed.offline == "TorrServer не отвечает", "приговор упаковке снят, показ ждёт"
    rows = _events(tmp_path / "trace")
    assert [r["asked"] for r in rows if r["event"] == "offline"] == [True]


def test_a_packing_failure_on_a_healthy_source_still_ends_the_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Источник в порядке, а упаковка сдалась - это по-прежнему конец показа с ошибкой."""
    from torrcast import cli

    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    feed.fatal = "ffmpeg сдался: Invalid data found"
    service = _Service()

    with pytest.raises(InfraError, match="упаковка оборвалась"):
        cli._hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]


def test_the_source_is_never_asked_while_the_picture_is_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пока идёт картинка, источник не спрашивают ни разу.

    Ограждение горячего пути: показ не имеет права ждать ни журнал, ни лишний запрос -
    вопросы источнику появляются только там, где показ уже кончается. Здесь показ идёт
    ровно так, как ему положено: приёмник играет, упаковка жива, - и ни один запрос к
    источнику не уходит.
    """
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    feed = _feed_with_segments(tmp_path)
    service = _Service()
    asked: list[str] = []
    supply = _supply(service)

    def spy(_self: Any) -> str:
        asked.append("?")
        return ""

    monkeypatch.setattr(type(supply), "check", spy)
    receiver = _FakeReceiver([(200.0, "PLAYING"), (210.0, "PLAYING"), (220.0, "PLAYING")])

    cli._hold(receiver, feed, None, None, supply)

    assert asked == [], "живой показ источник не спрашивает"


def test_a_show_that_never_started_still_names_the_dead_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Показ, не сдвинувшийся с нуля, кончается строкой про ИСТОЧНИК, а не про приёмник.

    Сюда приходит самый обидный случай: картинка так и не поехала, поднимать нечего и
    неоткуда (:class:`torrcast.cli._Revival` без позиции не работает), - и человек получал
    «приёмник не досмотрел поток» при живом приёмнике и мёртвой службе раздач. Спросить
    источник тут стоит тех же двух запросов, а показ уже кончился: горячего пути нет.
    """
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    service = _Service(up=False)
    supply = _supply(service)

    with pytest.raises(InfraError, match="источник не читается \\(TorrServer не отвечает\\)"):
        cli._blame_the_end(supply)


def test_a_show_that_never_started_blames_the_receiver_when_the_source_is_fine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Источник в порядке - строка остаётся прежней, и это правильно."""
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    with pytest.raises(InfraError, match="приёмник не досмотрел поток"):
        cli._blame_the_end(_supply(_Service()))


def test_a_source_that_came_back_by_itself_is_still_the_one_to_blame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Служба поднялась за три секунды - и всё равно виновата она, а не приёмник.

    Замер на стенде: перезапуск службы раздач стоит 3.0-3.1 с недоступности, а терпение
    приёмника - минуты. К мгновению, когда показ признан погасшим, служба уже отвечает, и
    вопрос «сейчас всё хорошо?» сам по себе оправдал бы её. Доказательство аварии - в том,
    что раздачу пришлось возвращать магнитом: без падения службы её никто не терял бы.
    """
    from torrcast import cli, trace

    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path / "trace"))
    (tmp_path / "trace").mkdir()
    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    service = _Service(listed=False, files=False)  # служба уже поднялась, но список пуст

    cli._hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00 (TorrServer перезапускался - раздачу вернул магнитом)" in printed
    assert service.added == [MAGNET], "раздача вернулась магнитом, а не голым хэшем"
    rows = _events(tmp_path / "trace")
    assert next(r for r in rows if r["event"] == "dark")["why"] == (
        "TorrServer перезапускался - раздачу вернул магнитом"
    )


def test_the_source_is_asked_more_than_once_before_it_is_believed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Один вопрос источнику - мало: умирающая служба отвечает как живая.

    Замер на живой службе (05:37:48.3 - 05:37:51.5): все три секунды своей остановки
    TorrServer отвечал на ``/echo`` и отдавал список раздач, а показ умирает как раз
    внутри этого окна. Здесь служба тоже «здорова» на первых вопросах и теряет раздачу
    на третьем - и виноватым всё равно называется источник.
    """
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    service = _Service()
    asked: list[int] = []
    real = type(service).listed

    def slow_death(self: _Service, torrent_hash: str) -> bool:
        asked.append(1)
        if len(asked) >= 3:
            self._listed = False
        return bool(real(self, torrent_hash))

    monkeypatch.setattr(_Service, "listed", slow_death)

    with pytest.raises(InfraError, match="источник не читается"):
        cli._blame_the_end(_supply(service))

    assert len(asked) >= 3, "источник спрошен несколько раз, а не единожды"
    assert service.added == [MAGNET], "заметив пропажу, раздачу вернули магнитом"


def test_the_picture_is_proved_by_a_moving_pointer_not_by_the_word_playing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``PLAYING`` при стоящем указателе - это ещё не картинка, и флажок ему не полагается.

    🔴 Замер на живом Q70D (заход в тяжёлое место, сплошной перекод): приёмник отвечает
    ``PLAYING`` на 8.2-й секунде, а указатель стоит на месте захода ещё 6.0 с - до тех
    пор, пока показ не выложил ВТОРОЙ кусок. То есть каждое «старт NN с» было занижено
    на 5-6 с ровно там, где человеку хуже всего. Здесь показ дожидается сдвига указателя.
    """
    from torrcast import cli
    from torrcast.stream import playing_flag

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    feed = _feed_with_segments(tmp_path)
    # Приёмник говорит «играю», не двигая указатель, и только потом трогается с места.
    stuck = _FakeReceiver([(300.0, "PLAYING"), (300.0, "PLAYING"), (0.0, "IDLE")])

    cli._hold(stuck, feed)

    assert not playing_flag(feed.out).exists(), "указатель стоял - картинки не было"

    feed = _feed_with_segments(tmp_path)
    moved = _FakeReceiver([(300.0, "PLAYING"), (300.5, "PLAYING"), (0.0, "IDLE")])

    cli._hold(moved, feed)

    assert playing_flag(feed.out).exists(), "указатель пошёл - вот это и есть картинка"


def test_the_mock_waits_for_as_much_film_as_the_receiver_gathers_before_the_first_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Заглушка не показывает кадр раньше, чем показ набрал запас живого приёмника.

    🔴 Замер на живом Q70D (:attr:`torrcast.profile.Profile.start_buffer`): на сетке по 8 с
    указатель тронулся только со ВТОРЫМ куском (16 с фильма), на сетке по 2.5 с - с
    четвёртым (10 с), а на третьем (7.5 с) ещё стоял. Заглушка объявляла картинку по
    первому же сдвигу своего декодера, то есть сухой прогон был бодрее живого ТВ на те
    самые секунды, из-за которых старт и меряют.
    """
    from torrcast.cast import MockReceiver, Position
    from torrcast.profile import CAUTIOUS

    assert CAUTIOUS.start_buffer == 10.0, "замер: столько фильма Q70D копит до первого кадра"

    mock = MockReceiver()
    monkeypatch.setattr(MockReceiver, "_over", lambda self: False)
    mock._pos = Position(300.0, 0.0, True)

    # Один кусок по 8 с впереди - живой приёмник тут ещё копит и кадра не показывает.
    assert mock.position(front=308.0).state == "BUFFERING", "8 с фильма приёмнику мало"
    mock._pos = Position(300.5, 0.0, True)
    # Второй кусок пришёл - запас перевалил за десять секунд, вот теперь картинка.
    assert mock.position(front=316.0).state == "PLAYING", "16 с - приёмник трогается"
    mock._pos = Position(301.0, 0.0, True)
    assert mock.position(front=303.0).state == "PLAYING", "копит он один раз, на заходе"
