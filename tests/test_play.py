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

from tests.conftest import CLIP_SECONDS, FakeProc, band_db, fake_packer, free_port
from tests.fakes.clock import WALL_ORIGIN, FakeClock
from tests.fakes.show_unit import FakeShowUnit
from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.adapters.filesystem.state.state import State
from torrcast.adapters.http_server.hls_base import hls_base
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.adapters.stream_pack.playing_flag import playing_flag
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.supply import Supply
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS, PACK_DIR
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.revive_settings import REVIVE_DROP, REVIVE_LIMIT, REVIVE_PAUSE, REVIVE_TRIES
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.start_settings import PAUSE_SECONDS
from torrcast.domain.worker_settings import WORKER_DUR, WORKER_META
from torrcast.usecases.choice._ctl import _ctl, _Steerable
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.playback._launch import _await_playing
from torrcast.usecases.playback._play import _play
from torrcast.usecases.playback._show_end import _blame_the_end, _handover
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.revive_playback._revival import _Revival
from torrcast.usecases.start_budget import START_BUDGET
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.watch import Watch as _Watch


class _Wired(ChromecastReceiver):
    """Живой приёмник, у которого вместо сети - подставное устройство.

    Всё остальное в нём настоящее: сторож подвиса, счёт смертей, перешагивание куска -
    ровно то, что и проверяется. Подменять их у общего класса нельзя: подмена дожила бы
    до соседнего теста, а зависимость эта - конструкторская.
    """

    def __init__(self, device: Any, address: str = "10.0.0.50", **rest: Any) -> None:
        super().__init__(address, **rest)
        self.device = device

    def _device(self) -> Any:
        return self.device


class _Reporting(_Wired):
    """Тот же приёмник, но статус берётся у подставного устройства, а не по сети."""

    def _status(self) -> Any:
        return self.device.status


class _Silenced(ChromecastReceiver):
    """Приёмник без сети: LOAD, перезапуск приложения и ожидание картинки - записи."""

    def __init__(self, address: str = "10.0.0.50", **rest: Any) -> None:
        super().__init__(address, **rest)
        self.loads: list[float] = []
        self.restarts = 0

    def _restart_app(self) -> None:
        self.restarts += 1

    def _load(self, at: float = 0.0, paused: bool = False) -> None:
        self.loads.append(at)

    def _settle(self, budget: float) -> bool:
        return True


class _Free(_Silenced):
    """То же самое, но экран всегда свободен: чужой показ тут не проверяется."""

    def _free(self) -> bool:
        return True


class _Opening(MockReceiver):
    """Заглушка, которая заход только записывает: проверяется решение, а не декодер."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.opens: list[float] = []

    def _open(self, url: str, at: float = 0.0) -> None:
        self.opens.append(at)


class _Quiet(Feed):
    """Раздача, которая упаковку не поднимает: проверяется учёт обрывов, а не ffmpeg."""

    def restart(self, slot: int) -> None:
        return None


def test_a_release_without_a_video_file_is_a_verdict_not_an_infra_error() -> None:
    """«Образ диска» - приговор раздаче (:class:`NotFoundError`), а не сбой инфраструктуры.

    Типом этого отказа пользуется отбор (:func:`~torrcast.usecases.select._verdict._silenced`):
    InfraError читается молчанием роя, и раздача-журнал («lainzine 1-5» по запросу «lain», TC-399)
    числилась бы неотозвавшейся, хотя про неё известно всё.
    """
    from torrcast.adapters.stream_probe.pick_video_file import pick_video_file
    from torrcast.domain.not_found_error import NotFoundError
    from torrcast.domain.torr_file import TorrFile

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
    (:mod:`torrcast.domain.frames.mkv`), а источник у этих тестов — файл на диске, читать
    который тем же способом неоткуда. Сетка по кадрам проверяется отдельно, ffmpeg'ом, в
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
    """Опорные кадры ролика — то же, что показ берёт из индекса mkv.

    Индекс разбирает :mod:`torrcast.domain.frames.mkv`.

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
    assert "gaps 0" in printed and "no CORS 0" in printed
    decoded = float(printed.split("decoded ")[1].split(" ")[0])
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
    assert "video hevc - recoding it whole on the fly" in printed, "решение говорится вслух"
    assert "тяжёлых кусков" not in printed, "посегментный кодировщик тут не поднимается"
    assert "gaps 0" in printed
    decoded = float(printed.split("decoded ")[1].split(" ")[0])
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "приёмник встал посреди показа"
    assert kept, "ни одного выложенного сегмента поймать не удалось"
    for path in kept:
        codecs = {s["codec_type"]: s["codec_name"] for s in _probe(path)}
        assert codecs["video"] == "h264", f"{path.name}: на ТВ уехал {codecs['video']}"
        assert codecs["audio"] == "aac", f"{path.name}: звук всегда AAC"


def test_the_whole_show_plays_the_track_from_a_file_beside_the_video(
    clip: str,
    clip_voice: str,
    tls: tuple[str, str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-305. Показ целиком на дорожке, лежащей отдельным файлом рядом с видео.

    Тут проверяется не команда ffmpeg, а сам показ: цепочка упаковка → раздача → приёмник
    отыгрывает весь ролик, приёмник не встаёт ни на одном стыке, а в пойманных с раздачи
    кусках звучит ВТОРОЙ файл (660 Гц), а не 440 Гц самого видео. Ровно так выглядит
    спасённая раздача: внутри видео звук чужой, русский лежит рядом отдельным файлом.
    """
    config = config_for(tmp_path, tls)
    kept: list[Path] = []
    where = tmp_path / "kept"
    where.mkdir()
    stop = threading.Event()
    watcher = threading.Thread(target=_grab_segments, args=(config, where, kept, stop), daemon=True)
    watcher.start()
    try:
        played = _play(
            config, clip, 0, "тест", _Clock(), duration=float(CLIP_SECONDS), voice=clip_voice
        )
    finally:
        stop.set()
        watcher.join(timeout=10)

    printed = capsys.readouterr().out
    assert played == 0
    assert "gaps 0" in printed
    decoded = float(printed.split("decoded ")[1].split(" ")[0])
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "приёмник встал посреди показа"
    assert kept, "ни одного выложенного сегмента поймать не удалось"
    for path in kept:
        assert band_db(path, 660) > band_db(path, 440) + 10, f"{path.name}: на ТВ уехал звук видео"


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
    enough = threading.Event()
    killer = threading.Thread(
        target=_kill_when_playing, args=(config, str(tmp_path), enough), daemon=True
    )
    killer.start()
    try:
        with pytest.raises(InfraError) as caught:
            _play(config, clip, 0, "тест", _Clock(), duration=float(CLIP_SECONDS))
    finally:
        enough.set()  # показ сдался - сносить больше некого
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


def _kill_when_playing(config: Config, pattern: str, enough: threading.Event) -> None:
    """Сносить упаковку, как только она поднимется, — и так пока показ не сдастся.

    Ждём кусок в каталоге прогона, а не снаружи: наружу он попадёт только после
    :meth:`Packer.publish`, и к тому времени можно не успеть вклиниться.

    ``enough`` кончает поток сразу: без отмашки он доживал до своего срока уже в чужой
    пробе и сносил бы её процессы.
    """
    out = Path(config.hls_dir)
    deadline = time.monotonic() + 60
    while not enough.is_set() and time.monotonic() < deadline:
        if list(out.glob("**/v*.ts")):
            for pid in _own_pids(pattern):  # только свои: соседний прогон не наше дело
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
        enough.wait(0.3)


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
        from torrcast.domain.position import Position

        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 0.0, state in {"PLAYING", "BUFFERING"}, state)


def _feed_with_segments(tmp_path: Path, kind: type[Feed] = Feed) -> Feed:
    """Упаковка на 60 готовых сегментов ровной сетки; ffmpeg за ней настоящий не стоит.

    ``kind`` - какой раздачей притвориться: наследник нужен там, где проверяется решение
    показа, а перезапуск упаковки должен остаться записью, а не ffmpeg.
    """
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(60):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = kind(source="", audio=0, out=out, grid=Grid.uniform(7200.0), keep=40.0, wait=0.0)
    feed.packer = fake_packer(out, first=0)
    return feed


def test_the_show_sweeps_ram_behind_the_receiver_while_it_plays(tmp_path: Path) -> None:
    """Показ следит ровно за двумя вещами: жива ли упаковка и что убрать из tmpfs.

    Перемотку он больше не ловит вовсе — приёмник видит весь фильм и мотает сам,
    а раздача пакует то место, которое он попросил.
    """

    feed = _feed_with_segments(tmp_path)
    receiver = _FakeReceiver([(200.0, "PLAYING"), (0.0, "IDLE")])

    _hold(receiver, feed, clock=FakeClock(1000.0))

    edge = feed.grid.slot_at(160.0)
    left = sorted(int(path.name[1:-3]) for path in feed.out.glob("v*.ts"))
    assert left == list(range(edge, 60)), "позади показа держим окно, остальное - из RAM"


def test_a_pause_on_the_remote_stops_packing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Пауза пультом: упаковку гасим (иначе tmpfs набивается впрок), показ остаётся жив.

    Возобновлять её показу не нужно: человек снимет паузу, приёмник попросит следующий
    сегмент, и раздача начнёт паковать с этого самого места сама.

    Пауза тут выдерживается настоящая - дольше :data:`torrcast.domain.start_settings.PAUSE_SECONDS`,
    - но не выжидается: часы показа свои (:class:`torrcast.ports.clock.Clock`), и опрос раз в 2 с
    двигает их сам.
    """

    feed = _feed_with_segments(tmp_path)
    held = int(PAUSE_SECONDS / 2.0) + 2  # опрос показа идёт раз в 2 с
    receiver = _FakeReceiver([*[(42.0, "PAUSED")] * held, (0.0, "IDLE")])

    _hold(receiver, feed, clock=FakeClock(1000.0))

    assert feed.halted() and feed.packer is not None and feed.packer.poll() == -15, (
        "ffmpeg завершён, а не остановлен сигналом"
    )
    assert "пауза на пульте" in capsys.readouterr().out


def test_the_diagnostic_remote_reaches_the_receiver_once(tmp_path: Path, remote: Path) -> None:
    """Диагностический пульт (``TORRCAST_CTL``): команда доезжает до приёмника ровно раз.

    Проверяется то, ради чего он написан: seek идёт **владеющим сендером** (тот же объект,
    что держит показ), файл съедается, и повторно та же команда не исполняется — иначе
    одна опечатка мотала бы фильм на каждом опросе.
    """

    seen: list[tuple[str, float]] = []

    class _Remote(_FakeReceiver):
        def seek(self, pos: float) -> None:
            seen.append(("seek", pos))

        def pause(self) -> None:
            seen.append(("pause", 0.0))

        def resume(self) -> None:
            seen.append(("play", 0.0))

    remote.write_text("seek 1200.5", "utf-8")
    feed = _feed_with_segments(tmp_path)
    receiver = _Remote([(200.0, "PLAYING"), (210.0, "PLAYING"), (0.0, "IDLE")])

    _hold(receiver, feed, clock=FakeClock(1000.0))

    assert seen == [("seek", 1200.5)], "команда исполнена один раз и владеющим сендером"
    assert not remote.exists(), "команда одноразовая - файл съеден"


def test_the_diagnostic_remote_is_absent_without_the_variable(tmp_path: Path) -> None:
    """Без ``TORRCAST_CTL`` пульта нет вовсе: на счастливом пути этот код не работает."""

    ctl = tmp_path / "ctl"
    ctl.write_text("seek 1200.5", "utf-8")
    feed = _feed_with_segments(tmp_path)

    _hold(_FakeReceiver([(200.0, "PLAYING"), (0.0, "IDLE")]), feed, clock=FakeClock(1000.0))

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

    def wall(self) -> float:
        """Стенная стрелка идёт вместе с монотонной, но со своей отметки.

        Одно и то же число на обеих шкалах прятало бы от проверок ровно ту путаницу,
        ради которой стенные часы вынесены в отдельную ручку порта.
        """
        return WALL_ORIGIN + self.now


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
        from torrcast.domain.position import Position

        if self.back_at and self.clock.now - self.began >= self.back_at:
            self.feed.offline = ""  # раздача снова читается
            self.warmer.warmed += 10.0  # и прогрев потащил новые куски
        if self.left > 0:
            self.left -= 1
            return Position(self.at, self.dur, True, "PLAYING")
        return Position(0.0, self.dur, False, "IDLE")

    def replay(self, at: float) -> float:
        self.replays.append(at)
        if not self.takes:
            return NOT_RAISED
        # Показ поднялся и доехал до титров - дальше приёмник гаснет уже законно.
        self.at, self.left = self.dur * 0.96, 2
        return at


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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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

    clock, feed, warmer, receiver = _dark(tmp_path, back_at=300.0)

    _hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "показ подняли, и ровно с той секунды, где смотрели"
    assert clock.now - 1000.0 >= 300.0, "до возврата сети приёмник не трогали ни разу"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00" in printed, "уход в темноту - честная строка, не молчание"
    assert "поднимаю показ с 0:20:00" in printed and "показ поднят с 0:20:00" in printed


def test_a_restored_source_spends_a_try_only_after_the_first_piece_is_ready(
    tmp_path: Path,
) -> None:
    """Ответившая служба ещё собирает метаданные и пиров - LOAD ждёт готового куска."""

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

    _hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "готовый кусок получил одну попытку подъёма"
    assert clock.now >= ready_at, "ответ службы сам по себе попытку не потратил"


class _Stillborn:
    """Приёмник, не давший НИ ОДНОГО кадра: LOAD взят, а указатель остался на нуле.

    🔴 Замер 16-08-2026 на живой приставке Xiaomi TV Stick («Харли Квинн» s1e1, 1080p
    5.6 Мбит/с, копия): LOAD взят на 4-й секунде, ``PLAYING`` на 0:00, через 2.0 с
    ``IDLE/ERROR`` без кода, два повтора LOAD - и всё. Позиция за весь сеанс не сдвинулась
    ни на десятую, и до правки на этом месте выходил рабочий юнит: зритель картины не
    видел вовсе. Тем и отличается от :class:`_Fading`, где показ БЫЛ.
    """

    def __init__(self, clock: _Ticker, dur: float = 7200.0, back: float = 0.0, takes: bool = True):
        self.clock, self.dur, self.back, self.takes = clock, dur, back, takes
        self.left = 1  # один опрос приёмник рапортует PLAYING - на нуле и без кадра
        self.pos = 0.0
        #: Насколько указатель уезжает за опрос. До подъёма - ноль, и это не мелочь:
        #: неподвижный указатель при слове ``PLAYING`` и есть «кадра не было».
        self.step = 0.0
        self.replays: list[float] = []

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self, quit_app: bool = False) -> None:
        pass

    def position(self, front: float = 0.0) -> Any:
        from torrcast.domain.position import Position

        if self.left > 0:
            self.left -= 1
            pos, self.pos = self.pos, self.pos + self.step
            return Position(pos, self.dur, True, "PLAYING")
        return Position(0.0, self.dur, False, "IDLE")

    def replay(self, at: float) -> float:
        self.replays.append(at)
        if not self.takes:
            return NOT_RAISED
        # Поднялся - и доиграл до титров: дальше приёмник гаснет уже законно.
        self.pos, self.left, self.step = self.dur * 0.96, 3, 30.0
        return self.back


def test_a_show_that_never_gave_a_frame_is_raised_from_the_start_of_the_picture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Отвал на 0:00 поднимается тем же путём, что и отвал посреди фильма.

    🔴 Живые прогоны владельца 15-08-2026 на приставке: пять стартов, две смерти на 0:00,
    и разница между «фильм досмотрен целиком» и «зритель не увидел ничего» была ровно
    одна - успел ли сдвинуться указатель. Успел (0:02) - лестница поднимала показ; остался
    на нуле - рабочий юнит выходил, а перед человеком оставался чёрный экран. Лестница
    чинила показ, который БЫЛ, и не чинила показа, которого не было.

    Ноль здесь - законное место картины, а не «поднимать неоткуда»: показ, умерший на
    первой секунде, обязан подниматься с первой секунды. Ответ о подъёме от этого не
    портится - отказ у приёмника свой (:data:`torrcast.domain.not_raised.NOT_RAISED`), и подъём с
    начала фильма больше не читается как «приёмник показ не взял».
    """

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    receiver = _Stillborn(clock)

    _hold(receiver, feed, None, None, clock=clock)

    assert receiver.replays == [0.0], "показ подняли ровно с того места, где он умер"
    printed = capsys.readouterr().out
    assert "показа не было ни кадра (заводили с 0:00:00)" in printed, (
        "«показ погас» тут враньё: гаснуть было нечему"
    )
    assert "показ поднят с 0:00:00" in printed, "подъём с начала картины - это удача"
    assert "приёмник показ не взял" not in printed, "нельзя звать отказом поднятый показ"


def test_a_resumed_show_that_never_gave_a_frame_goes_back_to_its_own_middle(
    tmp_path: Path,
) -> None:
    """Кадра не было, но фильм смотрят с 20-й минуты - туда показ и поднимают.

    ⚠️ Закладка в этот момент пуста (зритель не видел ничего), и брать её за место
    подъёма нельзя: ноль отправил бы человека в начало картины, которую он смотрит с
    середины. Место захода показ помнит сам.
    """

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    receiver = _Stillborn(clock, back=1200.0)

    _hold(receiver, feed, None, None, clock=clock, start=1200.0)

    assert receiver.replays == [1200.0], "подъём идёт в место захода, а не в начало фильма"


def test_a_show_that_never_gave_a_frame_gives_up_out_loud(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Лестница исчерпана, кадра так и нет - и это сказано, а не проглочено.

    Молчание тут дороже всего на стыке серий: консоли рядом нет, и кроме журнала показа
    сказать о беде некому (:func:`torrcast.usecases.playback._show_end._blame_the_end`, ``cast
    status``).
    """

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    receiver = _Stillborn(clock, takes=False)

    _hold(receiver, feed, None, None, clock=clock)

    assert receiver.replays == [0.0] * REVIVE_TRIES, "попытки конечны и все - с нуля"
    printed = capsys.readouterr().out
    assert "приёмник показ не взял" in printed and "показ поднять не удалось" in printed


def test_a_start_the_receiver_refused_is_handed_to_the_ladder_not_to_the_grave(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Приёмник не взял первый LOAD вовсе - показ ведёт лестница, а юнит не выходит.

    Отказ загрузки - не конец показа
    (:class:`torrcast.domain.start_refused_error.StartRefusedError`): приёмник в сети, фильм на
    месте, упаковка идёт, и не хватает ровно одного захода в чистое приложение. Картинка, добытая
    лестницей, называется вслух - иначе в журнале показа не осталось бы ни строки о том, что чёрный
    экран кончился.
    """

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    receiver = _Stillborn(clock)
    receiver.left = 0  # старт не взят вовсе: приёмник молчит с самого первого опроса

    _hold(receiver, feed, None, None, clock=clock, raised=False)

    assert receiver.replays == [0.0], "показ подняли, а не похоронили"
    assert "картинка пошла с" in capsys.readouterr().out


def test_a_show_that_never_gave_a_frame_names_that_and_not_undershown() -> None:
    """Последнее слово показа: «картинки не было ни разу», а не «не досмотрел поток».

    Для того, кто сидит перед экраном, это две разные аварии, и вторая дороже: «включил и
    не включилось» стоит выше на лестнице цели, чем оборванный на середине показ.
    """

    with pytest.raises(InfraError, match="картинки не было ни разу: приёмник не взял показ"):
        _blame_the_end(_supply(_Service()), shown=False, clock=FakeClock())
    with pytest.raises(InfraError, match="картинки не было ни разу: источник не читается"):
        _blame_the_end(_supply(_Service(up=False)), shown=False, clock=FakeClock())


def test_a_dark_show_gives_up_after_a_limited_number_of_tries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Попыток конечное число, и между ними держится выдержка.

    Бесконечный цикл LOAD в приёмник недопустим: терпение у него своё, а экран после
    смерти сессии ещё 301 с занят его же приложением (замер; наказания за 404 при этом
    нет вовсе - ноль секунд). Сеть вернулась, а показ всё равно не встаёт - значит дело не
    в сети, и упираться дальше нечего: гаснем честно, `cast` продолжит с места.
    """

    clock, feed, warmer, receiver = _dark(tmp_path, takes=False, back_at=300.0)

    _hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0] * REVIVE_TRIES, "попытки конечны и все - с места"
    assert clock.now - 1000.0 >= 300.0 + 2 * REVIVE_PAUSE, "между попытками выдержка"
    printed = capsys.readouterr().out
    assert "приёмник показ не взял" in printed
    assert "показ поднять не удалось" in printed and "cast продолжит с 0:20:00" in printed


def test_a_network_that_never_returns_ends_the_show_exactly_as_before(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Сеть так и не вернулась - фолбэк: гаснем честно, ни одного LOAD в приёмник.

    Это ровно сегодняшнее поведение, и оно обязано остаться: показ кончается, позиция уже
    в состоянии, `cast` продолжит с места. Ново здесь одно - показ не уходит молча в ту же
    секунду, а ждёт сеть, пока ждать есть смысл.
    """

    clock, feed, warmer, receiver = _dark(tmp_path)

    expected_end = _hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [], "мёртвая сеть - в приёмник не ушло ни одного LOAD"
    assert expected_end, "исчерпанные попытки - ожидаемый фолбэк, а не падение юнита"
    assert clock.now - 1000.0 > REVIVE_LIMIT, "ждали ровно столько, сколько обещали"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00" in printed and "cast продолжит с 0:20:00" in printed


def test_the_darkness_is_named_in_the_state_and_not_called_a_show(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
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

    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    warmer.warmed = 0.0  # прогретого нет - в темноте играть нечем
    entry = Entry(title="ролик", magnet=MAGNET, pos=0.0, dur=7200.0)
    watch = _Watch(key="movie:ролик:2026", entry=entry, every=0.0)
    seen: list[tuple[float, str]] = []
    clock.ticks.append(lambda _s: seen.append(_dark_mark(watch.key)))

    _hold(receiver, feed, watch, warmer, _supply(_Service(up=False)), clock=clock)  # type: ignore[arg-type]

    marked = [mark for mark in seen if mark[0]]
    assert marked, "темнота не названа темнотой ни разу за все 900 с"
    assert {why for _at, why in marked} == {"TorrServer не отвечает"}, "причина не та"
    assert len(marked) * 2 > REVIVE_LIMIT * 0.9, "отметка появилась не сразу, а под конец"
    assert seen[0] == (0.0, ""), "у живой картинки отметки темноты нет"
    printed = capsys.readouterr().out
    assert "(TorrServer не отвечает) - картинки нет; источник не вернулся" in printed, (
        "человеку про темноту сказано числом, а не строкой «экран: … · IDLE»"
    )
    # Граница сидит на такте опроса: с учащённым шагом окна старта последняя строка
    # ложится ровно на срок сдачи.
    assert "погашу через 0:00:00" in printed, "не сказано, когда показ сдастся сам"
    assert printed.count("экран:") == 1, "экраном названа только живая картинка, до темноты"
    assert "показ обеспечен до" not in printed, "обеспечивать в темноте уже нечего"


def test_the_darkness_mark_goes_away_with_the_picture(tmp_path: Path) -> None:
    """Сеть вернулась, показ поднят - отметки темноты в состоянии больше нет.

    Иначе ``cast status`` звал бы погасшим показ, который давно идёт: отметка обязана
    сниматься тем же, чем ставится, и в ту же секунду.
    """

    clock, feed, warmer, receiver = _dark(tmp_path, back_at=300.0)
    entry = Entry(title="ролик", magnet=MAGNET, pos=0.0, dur=7200.0)
    watch = _Watch(key="movie:ролик:2026", entry=entry, every=0.0)
    seen: list[tuple[float, str]] = []
    clock.ticks.append(lambda _s: seen.append(_dark_mark(watch.key)))

    _hold(receiver, feed, watch, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "показ подняли - иначе проверять нечего"
    assert [mark for mark in seen if mark[0]], "темнота была и отмечена"
    assert _dark_mark(watch.key) == (0.0, ""), "картинка идёт, а запись зовёт показ погасшим"


def test_the_darkness_reason_follows_a_returning_source(tmp_path: Path) -> None:
    """Источник уже отвечает - текущая строка больше не называет его мёртвым."""

    clock, feed, warmer, receiver = _dark(tmp_path)
    service = _Service(up=False)
    revival = _Revival(supply=_supply(service), clock=clock)

    assert revival.resurrect(receiver, feed, warmer, 1200.0)  # type: ignore[arg-type]
    assert revival.why == "TorrServer не отвечает"
    service.up = True

    assert revival.resurrect(receiver, feed, warmer, 1200.0)  # type: ignore[arg-type]
    assert revival.why == "источник вернулся - жду готовности потока"


def _dark_mark(key: str) -> tuple[float, str]:
    """Отметка темноты из состояния: когда погасло и почему."""
    entry = State.load().get(key)
    return (entry.dark, entry.dark_why) if entry is not None else (0.0, "")


def test_a_warmed_movie_is_revived_without_waiting_for_the_network(tmp_path: Path) -> None:
    """Фильм лёг на диск целиком - воскрешение не ждёт сети ни секунды: смотреть есть что."""

    clock, feed, warmer, receiver = _dark(tmp_path, warmed=7200.0, done=True)

    _hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [1200.0], "подняли сразу и с сохранённого места"
    assert clock.now - 1000.0 < REVIVE_PAUSE, "ждать возврата сети было незачем"


def test_a_finished_movie_is_not_resurrected(tmp_path: Path) -> None:
    """Титры - не авария: досмотренный фильм гаснет и остаётся погашенным."""

    clock, feed, warmer, receiver = _dark(tmp_path, offline="", at=7100.0)

    _hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [], "конец показа не воскрешают"
    assert clock.now - 1000.0 < REVIVE_PAUSE, "и не ждут на нём ни сети, ни выдержки"


class _Nudged:
    """Приёмник, застрявший в BUFFERING: сторож подвиса гонит указатель вперёд по 8 с.

    Ровно замер живого Q70D: картинка стоит на 2:39, а сторож
    (:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver._nudge`)
    двенадцать раз прыгает вперёд, вытаскивая приёмник из зависания, и уводит позицию на 4:15 - на
    1:36 впереди последнего кадра, который человек видел. Картинки всё это время нет: состояние
    остаётся ``BUFFERING``, и только его отличие от ``PLAYING`` и говорит, где кончился показ, а где
    начался указатель. Потом приёмник бросает показ насовсем.
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
        from torrcast.domain.position import Position

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

    def replay(self, at: float) -> float:
        self.replays.append(at)
        return NOT_RAISED  # приёмник так и не вернулся: показ кончится честной темнотой


def test_the_bookmark_holds_the_last_frame_seen_not_where_the_watchdog_drove(
    tmp_path: Path,
) -> None:
    """Сторож подвиса увёл указатель на 1:36 вперёд - воскресаем с последнего КАДРА.

    Замер на живом Q70D: показ встал на 2:39, сторож сделал 12 нуджей по 8 с и довёл
    указатель до 4:15, а картинки не было ни секунды из этих полутора минут. Воскрешение
    при этом точное - оно поднимает ровно ту секунду, которую ему дали, - и потому человек
    продолжал с места, которого не видел, и молчаливый resume шёл туда же.

    Сторож здесь прав и не трогается: он вытаскивает приёмник из зависания, и прыгать ему
    есть чем только вперёд. Чинится закладка: место показа отмеряет глаз, а не указатель,
    то есть ``PLAYING``, а не ``BUFFERING``.
    """

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    feed.offline = "источник молчит дольше 45 с"
    warmer = _Warm()
    receiver = _Nudged(clock, feed, warmer, back_at=100.0)
    entry = Entry(title="ролик", magnet=MAGNET, pos=0.0, dur=7200.0)
    watch = _Watch(key="movie:ролик:2026", entry=entry, every=0.0)

    _hold(receiver, feed, watch, warmer, clock=clock)  # type: ignore[arg-type]

    assert receiver.replays == [159.0] * REVIVE_TRIES, "поднимаем с показанного кадра"
    assert entry.pos == 159.0, "и resume идёт туда же, а не на 4:15"


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
        from torrcast.domain.position import Position

        self.warmer.warmed += 5.0  # служба раздач жива весь показ - куски идут всегда
        if self.clock.now < self.until:
            self.at += 2.0
            return Position(self.at, 7200.0, True, "PLAYING")
        self.died = self.died or self.clock.now
        return Position(0.0, 7200.0, False, "IDLE")

    def replay(self, at: float) -> float:
        self.replays.append(at)
        self.when.append(self.clock.now)
        if self.refuses:
            self.refuses -= 1
            return NOT_RAISED  # 404 ещё не отпустил: LOAD приёмник не берёт
        if not self.revives:
            return NOT_RAISED
        self.revives -= 1
        self.refuses = 1 if self.revives else 0  # следующий обрыв начнётся так же
        self.at, self.until, self.died = at, self.clock.now + self.live, 0.0
        self.revived.append(at)
        return at


def test_a_receiver_that_dropped_the_show_gets_it_back_in_seconds_not_in_a_minute(
    tmp_path: Path,
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
    к этой аварии не подходит, и дальше снова минута
    (:data:`torrcast.domain.revive_settings.REVIVE_PAUSE`).
    """

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    feed.offline = ""  # упаковка на обрыв не жаловалась: рвался не источник
    warmer = _Warm()
    receiver = _Blinking(clock, warmer)

    _hold(receiver, feed, None, warmer, _supply(_Service()), clock=clock)  # type: ignore[arg-type]

    assert receiver.replays, "показ всё-таки поднимали - попытки не пропали вовсе"
    waited = receiver.when[0] - receiver.died
    assert waited >= REVIVE_DROP, "приёмнику всё же дали те секунды, что он просит"
    assert waited < REVIVE_PAUSE / 2, f"минуты чёрного экрана больше нет ({waited:.0f} с)"
    assert receiver.when[1] - receiver.when[0] >= REVIVE_PAUSE, (
        "а вот вторая попытка ждёт как прежде: первая не помогла - осторожничаем"
    )
    assert len(receiver.replays) == REVIVE_TRIES, "и попытки остались конечными"


def test_two_short_outages_do_not_eat_the_whole_stock_of_tries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Два коротких обрыва подряд - и оба показ переживает: запас отмерян обрыву.

    Замер на живом Q70D: за 13 минут показа два коротких обрыва израсходовали все три
    попытки, отмеренные на весь сеанс. Каждый обрыв показ пережил и человек не заметил
    ничего - но защиты на остаток вечера уже не осталось, и третий обрыв гасил бы показ
    насовсем при живых и приёмнике, и источнике.

    Возвращает запас не сам факт подъёма (это говорит приёмник), а прожитая после него
    минута настоящей картинки (:data:`torrcast.domain.revive_settings.REVIVE_LIVED`): мигающий показ
    так себе попытки не наотдаёт, и поток LOAD остаётся конечным.
    """

    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    feed.offline = ""
    warmer = _Warm()
    receiver = _Blinking(clock, warmer, refuses=1, revives=2)

    _hold(receiver, feed, None, warmer, _supply(_Service()), clock=clock)  # type: ignore[arg-type]

    assert len(receiver.revived) == 2, "оба обрыва показ пережил, а не только первый"
    assert receiver.revived[1] > receiver.revived[0], "второй раз поднялись дальше по фильму"
    printed = capsys.readouterr().out
    assert printed.count("показ поднят с ") == 2, "и человек увидел оба подъёма"


def test_the_dark_show_is_revived_only_on_a_free_receiver() -> None:
    """Воскрешаем только СВОЙ показ - той же аккуратностью, что и закрываем приложение.

    Пока нас не было, на том же ТВ могли начать смотреть другое: чужое приложение, чужая
    сессия в том же Default Media Receiver, чужой ``content_id`` в нашей. Перебивать такое
    нельзя ничем - ни LOAD, ни ``quit_app`` перед ним; показу остаётся честно погаснуть.
    """
    loads: list[float] = []
    aliens = [
        _FakeCast(app_id="Netflix"),
        _FakeCast(session="чужая"),
        _FakeCast(content="http://10.0.0.20:8010/cast.m3u8"),
    ]
    for alien in aliens:
        receiver = _receiver_on(alien)
        assert receiver.replay(1200.0) == NOT_RAISED, "чужой показ неприкосновенен"
        loads += receiver.loads
    assert loads == [], "в чужой показ не ушло ни одного LOAD"
    assert all(alien.log == [] for alien in aliens), "и приложение чужому не закрывали"

    for free in (_FakeCast(app_id=None), _FakeCast(app_id=ChromecastReceiver.BACKDROP_APP)):
        receiver = _receiver_on(free)
        assert receiver.replay(1200.0) == 1200.0, "экран свободен - показ поднимаем"
        assert receiver._peak == 1200.0, "сторож считает с того места, куда грузили"
        loads += receiver.loads
    assert loads == [1200.0, 1200.0], "по одному LOAD на свободный приёмник"


def test_a_release_that_never_plays_stops_at_the_profile_not_at_eleven() -> None:
    """Неигравший релиз: ровно столько повторов LOAD, сколько заявил профиль, - и честная
    строка вместо зависания в лестнице ожидания.

    Раньше лестница ожидания считала попытки временем бюджета, а не профилем: приёмник,
    роняющий каждый LOAD в IDLE/ERROR, получал их десяток подряд (на гейте - одиннадцать),
    всё глубже заваливаясь, а прогон висел в лестнице, пока его не прибивали руками. Теперь
    счётчик повторов LOAD один на весь показ, потолок ему - ``load_retries`` приёмника, и
    исчерпав его, показ возвращает управление честной строкой.
    """
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

        def play_media(self, url: str, _mime: str, current_time: float = 0.0, **_: Any) -> None:
            loads.append(current_time)

        def block_until_active(self, timeout: float = 30.0) -> None:
            pass

        def update_status(self) -> None:
            pass

        def quit_app(self, timeout: float = 10.0) -> None:
            pass

        def disconnect(self) -> None:
            pass

    class _Kept(ChromecastReceiver):
        """Чистое приложение под повтор тут не поднимается: та же лента LOAD, её и считаем."""

        def _restart_app(self) -> None:
            return None

    receiver = _Kept("10.0.0.50", clock=FakeClock())
    receiver._cast = _Silent()

    with pytest.raises(StartRefusedError) as err:
        receiver.play("http://10.0.0.10:8443/index.m3u8", "кино", at=1200.0)

    assert receiver.profile.load_retries == 2, "осторожный профиль - замер Q70D"
    assert len(loads) == 1 + receiver.profile.load_retries, (
        "первый LOAD и ровно load_retries повторов - не одиннадцать по бюджету времени"
    )
    assert loads[1:] == [1200.0] * receiver.profile.load_retries, "повтор уходит туда же"
    assert "did not start the show" in str(err.value), (
        "исчерпав попытки, показ гаснет честной строкой"
    )


def test_the_receivers_detailed_error_survives_pychromecast_parsing() -> None:
    """Код отказа снимается с сырого ответа, пока библиотека его не выбросила."""
    from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver

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


def test_the_receivers_detailed_error_is_taken_from_a_refused_load_too() -> None:
    """Код отказа снимается и со второго ответа приёмника - отказа самой загрузки."""
    from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver

    seen: list[dict[str, Any]] = []

    class _Controller:
        def _process_media_status(self, data: dict[str, Any]) -> None:
            seen.append(data)

        def _process_load_failed(self, data: dict[str, Any]) -> None:
            seen.append(data)

    receiver = ChromecastReceiver("10.0.0.50")
    controller = _Controller()
    receiver._catch_media_error(controller)

    controller._process_load_failed({"type": "LOAD_FAILED", "detailedErrorCode": 905})

    assert receiver._error_code == 905, "код отказа загрузки не потерян"
    assert len(seen) == 1, "обычный разбор отказа продолжился"

    controller._process_load_failed({"type": "LOAD_FAILED"})
    assert receiver._error_code == 905, "отказ без кода не стирает уже названную причину"


def test_a_receiver_without_load_failure_parsing_still_gets_its_error_hook() -> None:
    """Приёмник, у которого разбора отказа загрузки нет, снимается прежним путём."""
    from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver

    class _Controller:
        def _process_media_status(self, data: dict[str, Any]) -> None:
            return None

    receiver = ChromecastReceiver("10.0.0.50")
    controller = _Controller()
    receiver._catch_media_error(controller)

    controller._process_media_status(
        {"status": [{"playerState": "IDLE", "idleReason": "ERROR", "detailedErrorCode": 301}]}
    )
    assert receiver._error_code == 301, "код сетевого отказа снят и без второго канала"


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
        self.receiver.decoder.proc = FakeProc()  # type: ignore[assignment]
        self.receiver.decoder.start = at
        self.receiver.report.duration = self.dur
        self.receiver.decoder.pos = Position(at, self.dur, True)

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
        pos = self.receiver.decoder.pos
        if self.up and pos.playing:
            self.receiver.decoder.pos = Position(pos.pos + seconds, self.dur, True)

    def finish(self) -> None:
        """Показ доехал до титров, а следом кончился вход - ровно в этом порядке.

        Порядок тут и есть суть: место, с которого показ поднимают, - последнее, где он
        был живым, и у досмотренного фильма оно за порогом 95 %. Погаси декодер раньше -
        и титры сошли бы за аварию.
        """
        self.ending += 1
        if self.ending == 1:
            self.receiver.decoder.pos = Position(self.dur * 0.96, self.dur, True)
            return
        self.woke = 0.0
        self.receiver.decoder.proc.code = 0  # type: ignore[union-attr]
        self.receiver.decoder.pos = Position(self.dur * 0.96, self.dur, False)


class _Piped(MockReceiver):
    """Заглушка, у которой поток открывает подставной источник, а не ffmpeg.

    Источнику нужен сам приёмник (он двигает его указатель), поэтому связываются они
    после сборки: приёмник заводится первым и получает источник полем.
    """

    source: Any = None

    def _open(self, url: str, at: float = 0.0) -> None:
        self.source.open(url, at)


def _blinking(
    tmp_path: Path,
    patience: float = 6.0,
    **kwargs: Any,
) -> tuple[_Ticker, Feed, _Warm, MockReceiver, _Source]:
    """Показ на заглушке, под которым моргает источник - сухой прогон живой аварии.

    Терпение приёмника задаётся, а не выжидается: живьём медиасессия Samsung Q70D живёт
    23.5 с стоящей картинки, а его приложение - ещё 301 с после этого, и тест, честно
    простоявший их, никто гонять не станет. Часы у показа и у заглушки одни и свои
    (:class:`torrcast.ports.clock.Clock`): настоящий :mod:`time` тут не трогают вовсе, потому и
    исход не зависит от того, чем занята машина.
    """
    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    warmer = _Warm(warmed=600.0)
    receiver = _Piped(patience=patience, clock=clock)
    source = receiver.source = _Source(clock, receiver, feed, warmer, **kwargs)
    receiver.play("http://127.0.0.1:8010/index.m3u8", at=1200.0)
    return clock, feed, warmer, receiver, source


def test_a_blinking_source_takes_the_mock_receiver_dark_and_the_show_comes_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Источник моргнул - показ погас - источник вернулся - показ поднялся. На заглушке.

    Ровно этого сценария на сухом прогоне и не было: заглушка показ не бросала никогда,
    :class:`torrcast.usecases.choice._ctl._Revivable` не реализовывала, и живая авария (перезапуск
    TorrServer под показом) воскрешения не вызывала ни разу - и не могла.

    Терпение заглушки тут своё, но правила у него чужие, замеренные на живом Samsung Q70D:
    пока оно идёт, показ считается живым (``BUFFERING``) и приёмник тратит на картинку два
    своих перезабора куска по HTTP (повторами LOAD они не были никогда - сессия та же);
    кончилось - сессии нет, и позиция в ней читается нулём.
    """

    clock, feed, warmer, receiver, source = _blinking(tmp_path, back_at=120.0)

    _hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    first, own, revival = source.opens[0], source.opens[1:3], source.opens[3:]
    assert first == 1200.0, "показ начался с 20-й минуты"
    # Полсекунды сетки: между словом PLAYING и первым кадром опрос идёт раз в
    # FIRST_FRAME_POLL, и декодер заглушки успевает на полтика меньше.
    assert own == [1208.5, 1208.5], "приёмник потратил на пропавшую картинку свои два LOAD"
    assert revival == [1208.5], "воскрешение пришло снаружи - и ровно с места остановки"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:08" in printed, "заглушка бросила показ, а не досидела до конца"
    assert "сеть вернулась - поднимаю показ с 0:20:08" in printed
    assert "показ поднят с 0:20:08" in printed, "картинка вернулась, и заглушка это подтвердила"


def test_the_mock_receiver_burns_its_patience_before_it_drops_the_show(tmp_path: Path) -> None:
    """Терпение заглушки - не бутафория: пока оно идёт, показ живой и воскрешать нечего.

    Живой приёмник на стоящей картинке уходит в ``BUFFERING`` и держится примерно четыре
    минуты. Заглушка, гаснущая на первом же неподвижном опросе, звала бы воскрешение там,
    где настоящий ТВ ещё показывает фильм, - то есть врала бы в другую сторону.
    """
    clock, _, _, receiver, source = _blinking(tmp_path, dark_at=0.0)

    # ⚠️ Числа переписаны по замеру 09-08-2026 (живой Q70D, рапорт приёмника + tcpdump):
    # прежние «240 с» склеивали два РАЗНЫХ срока - смерть медиасессии (23.5 с) и уход
    # приложения с экрана (301 с), - а «повторы LOAD» на деле оказались перезаборами
    # куска по HTTP: media_session_id при них не менялся. Поведение теста не изменилось:
    # терпение он и раньше задавал сам, а проверяет он правила, а не цифры.
    assert CAUTIOUS.patience == 23.5, "замер: столько живёт медиасессия после стопа"
    assert CAUTIOUS.segment_retries == 2, "и ровно два перезабора куска внутри неё"

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
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Источник не вернулся - гаснем честно: попытки конечны, LOAD в приёмник не летит.

    Отрицательная половина того же сценария. Заглушка обязана уметь и её: показ, который
    поднимается на сухом прогоне всегда, доказывал бы ровно ничего.
    """

    clock, feed, warmer, receiver, source = _blinking(tmp_path)

    _hold(receiver, feed, None, warmer, clock=clock)  # type: ignore[arg-type]

    # Полсекунды сетки - от учащённого опроса между словом PLAYING и первым кадром.
    assert source.opens == [1200.0, 1208.5, 1208.5], "после своих двух повторов - ни одного LOAD"
    assert clock.now - 1000.0 > REVIVE_LIMIT, "ждали ровно столько, сколько обещали"
    printed = capsys.readouterr().out
    assert "показ погас на 0:20:08" in printed
    assert "показ поднять не удалось" in printed and "cast продолжит с 0:20:08" in printed


def test_the_mock_receiver_takes_a_load_right_after_a_404() -> None:
    """404 заглушка наказывает ровно столько, сколько сказано в профиле, - то есть нисколько.

    🔴 Ожидание переписано по замеру 09-08-2026 (живой Q70D, рапорт приёмника + tcpdump):
    наказание за 404 опровергнуто трижды - LOAD после него берётся даже быстрее обычного
    тёплого. Прежний тест закреплял ровно ту легенду, которую замер снял, и оставить его
    значило бы держать в сухом прогоне выдуманную аварию.

    Что от него осталось и почему: сам механизм наказания жив и берётся из профиля
    (:attr:`torrcast.domain.profile.Profile.sulk`) - мерили чистый 404 в здоровой сессии, и
    приёмник, который всё-таки обижается, должен настраиваться числом, а не правкой кода.
    На решение «держать запрос вместо 404» этот ноль не влияет: там своя причина.
    """
    clock = _Ticker()
    receiver = _Opening(clock=clock)
    receiver._url = "http://127.0.0.1:8010/index.m3u8"

    receiver.fetch.caught(_Answer(404))
    assert CAUTIOUS.sulk == 0.0, "наказания за 404 нет - замер снял его трижды"
    assert receiver.replay(1200.0) == NOT_RAISED, "картинки нет - врать о поднятом показе нельзя"
    assert receiver.opens == [1200.0], "но попытку приёмник принял сразу, не выжидая ни секунды"

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


def test_a_finished_packer_is_not_a_crash_but_a_serial_one_gives_up(tmp_path: Path) -> None:
    """Конец входа и обрыв — разные вещи, и показ обязан их различать.

    Код 0 — фильм упакован до конца, падать не с чего. Обрыв — повод начать заново с того
    места, где стоит приёмник; но если рвётся раз за разом, показ сдаётся честной строкой,
    а не крутит круг вечно.

    ⚠️ «Раз за разом» — это про ПРОГОНЫ, а не про опросы: каждый перезапуск даёт новый
    процесс, и наказывать за обрыв надо его, а не считать заново тот же труп на каждом
    запросе сегмента (их приходит по пять в секунду).
    """

    class _Again(Feed):
        """Раздача, у которой перезапуск - это новый процесс упаковки, и снова мёртвый."""

        def restart(self, slot: int) -> None:
            self.packer = fake_packer(self.out, first=0, code=-9)

    feed = _feed_with_segments(tmp_path, kind=_Again)
    assert feed.packer is not None

    feed.packer.proc.code = 0  # type: ignore[attr-defined]
    assert feed.segment(70) is None and feed.trouble() == "", "дошли до конца фильма"

    # Оборвался - это уже другой прогон: из кода 0 в убитый один и тот же процесс не ходит.
    feed.packer = fake_packer(feed.out, first=0, code=-9)
    for _ in range(feed.limit):
        feed.restarted = 0.0  # прогоны идут не подряд: защита «не толкаемся» тут не при чём
        feed.segment(70)
    assert feed.trouble() == "", "обрыв переживаем молча, пока попытки не кончились"

    feed.restarted = 0.0
    feed.segment(70)
    assert feed.trouble() == "убит сигналом 9"


def test_a_torn_input_tells_the_viewer_the_film_has_not_ended(tmp_path: Path) -> None:
    """Оборванный вход и доигранный фильм для зрителя выглядят одинаково - паузой.

    Вход, умерший на середине, ffmpeg отмечает НУЛЁМ
    (:meth:`torrcast.adapters.stream_pack.packer.Packer.finished`), и «упаковка оборвалась
    (молча, код
    0)» говорит человеку о нашем коде возврата, а не о его кино: он видит паузу и решает, что фильм
    кончился. Замер 15-08-2026, 80 обрывов входа на живом ffmpeg (457 прогонов): код 0 вышел во ВСЕХ
    457 - по коду эти два исхода не различаются вовсе.

    Обещать починку строка при этом не имеет права. Тот же замер развёл два мира начисто:
    вернулся источник - заново пакуется 76 раз из 76; не вернулся - 1 из 76 на второй
    попытке и 0 из 76 на третьей. На первом обрыве неизвестно, который из них перед нами,
    поэтому сказан факт, а не прогноз.
    """

    class _Torn(Packer):
        """Прогон, у которого вход умер на середине: ffmpeg вышел нулём, а фильм - нет."""

        def finished(self) -> bool:
            return False

    said: list[str] = []
    feed = _feed_with_segments(tmp_path, kind=_Quiet)
    feed.log = said.append

    # вход умер, ffmpeg вышел нулём
    feed.packer = fake_packer(feed.out, first=0, code=0, kind=_Torn)
    feed.restarted = 0.0
    feed.segment(70)
    assert said == ["вход оборвался на середине, фильм не кончился - начинаю заново, попытка 1"], (
        f"зрителю сказали не о фильме, а о коде возврата: {said}"
    )

    # Прогон, убитый сигналом, - это не оборванный вход, и выдавать его за него нельзя.
    said.clear()
    feed.packer = fake_packer(feed.out, first=0, code=-9)
    feed.restarted = 0.0
    feed.segment(70)
    assert said == ["упаковка оборвалась (убит сигналом 9) - начинаю заново, попытка 2"], (
        f"чужая беда названа обрывом входа: {said}"
    )


def test_one_dead_run_is_blamed_once_and_not_on_every_request(tmp_path: Path) -> None:
    """Один труп упаковки не съедает все попытки за полсекунды.

    Живой сценарий: TorrServer выронил раздачу посреди показа, вход мёртв, ffmpeg умирает
    сразу после старта — то есть внутри двух секунд, пока держит защита «не толкаемся».
    Пока обрыв считался на каждый запрос сегмента, три попытки сгорали за 0.8 с и показ
    умирал, ни разу по-настоящему не перезапустив упаковку.
    """
    feed = _feed_with_segments(tmp_path, kind=_Quiet)
    assert feed.packer is not None

    feed.packer.proc.code = -9  # type: ignore[attr-defined]
    feed.restarted = time.monotonic()  # перезапуск только что был - второй не нужен
    for _ in range(10):
        feed.segment(70)

    assert (feed.crashes, feed.trouble()) == (1, ""), "труп наказан один раз, показ жив"


def test_resume_starts_from_the_offset_and_ends_as_watched(
    clip: str, tls: tuple[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Тот же показ, но с середины: ffmpeg стартует с `-ss`, приёмник декодирует остаток,
    сторож кладёт в state абсолютную позицию, а на 95 % пишет «досмотрено».
    """
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
    decoded = float(printed.split("decoded ")[1].split(" ")[0])
    assert decoded >= CLIP_SECONDS - HLS_SEGMENT_SECONDS, "показ оборвался"
    assert f"упаковка с {offset:.1f} с" in printed, "показ начался с позиции, а не сначала"
    # 🔴 Заход упаковки на голову фильма тут - брак ЗАГЛУШКИ, а не показа: живой Q70D
    # первого сегмента при старте с середины не просит вовсе (:meth:`MockReceiver._from`).
    assert printed.count("упаковка с ") == 1, "упаковка сходила на голову плейлиста"
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


def test_a_stuck_receiver_is_nudged_only_when_the_packing_is_ahead() -> None:
    """Неподвижный BUFFERING — это две разные беды, и лечатся они по-разному.

    Замерено на живом Q70D: на 1:24 фильма приёмник встал намертво при 60 с
    готовой упаковки впереди, сам не ожил ни разу и оживал только от нашего ``seek``. А
    ровно так же выглядит приёмник, который честно ждёт упаковку, — и вот его трогать
    нельзя: прыжок уведёт показ в неупакованное место и заставит паковать заново.
    """
    jumps: list[float] = []
    receiver = _Wired(_FakeDevice(jumps))
    receiver._peak = 84.0

    receiver._nudge(84.0, front=144.0)
    assert jumps == [], "первый неподвижный тик - ещё не зависание"

    receiver._stall_since -= CAUTIOUS.stall_seconds
    receiver._nudge(84.0, front=88.0)
    assert jumps == [], "запаса впереди нет - приёмник ждёт нас, а не завис"

    receiver._nudge(84.0, front=144.0)
    assert jumps == [84.0 + CAUTIOUS.stall_skip], "еда на столе - расшевелить"


#: Сетка «Моаны» 2016 вокруг места, на котором показ умер: границы взяты у неё же.
_MOANA = Grid((0.0, 112.905, 124.583, 137.095, 148.940, 161.037), 6500.285, True)


def test_a_nudge_lands_past_the_segment_and_not_eight_seconds_ahead() -> None:
    """Прыжок мимо застрявшего куска обязан быть длиннее самого куска.

    Замер на «Моане» 2016: показ встал на 127.2 с внутри сегмента
    ``[124.583..137.095)``, а сторож прыгнул на 8 с — то есть в тот же сегмент, откуда
    и прыгал. Оба нуджа сеанса приземлились туда же, и застрявший кусок так и остался
    впереди: 5 мин 48 с показа сдвинули картинку на 2.4 с.
    """
    jumps: list[float] = []
    receiver = _Wired(_FakeDevice(jumps))
    receiver.next_cut = _MOANA.after
    receiver._peak = 127.2

    assert _MOANA.slot_at(127.2 + CAUTIOUS.stall_skip) == _MOANA.slot_at(127.2), (
        "замер: прежний шаг не выводил из сегмента вовсе"
    )

    receiver._nudge(127.2, front=200.0)
    receiver._stall_since -= CAUTIOUS.stall_seconds
    receiver._nudge(127.2, front=200.0)

    assert jumps == [137.095 + ChromecastReceiver.CUT_SLACK]
    assert _MOANA.slot_at(jumps[0]) == _MOANA.slot_at(127.2) + 1, "прыгнули ровно на кусок вперёд"


def test_a_segment_that_keeps_killing_the_show_is_stepped_over(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Показ, умирающий на одном куске, обязан однажды перешагнуть его, а не ходить кругом.

    Замер на «Моане» 2016: четыре смерти, три воскрешения и семь повторов LOAD подряд —
    и каждый круг возвращал приёмник на то же место, получая тот же исход, до самого
    конца сеанса. Первые смерти при этом законны: моргнувшую сеть от невоспроизводимого
    куска отличает только счёт.
    """
    receiver = _Free()
    loads = receiver.loads
    receiver.next_cut = _MOANA.after
    receiver._peak = 127.2

    assert receiver._reload() is True
    assert receiver._reload() is True
    assert loads == [127.2, 127.2], "первые смерти возвращают человека туда, где он смотрел"

    picture = 127.2
    pressure = picture + receiver.profile.start_buffer
    assert _MOANA.slot_at(picture) + 1 == _MOANA.slot_at(pressure), (
        "замер: декодер давится на кусок впереди картинки"
    )

    assert receiver.replay(picture) == 148.940 + ChromecastReceiver.CUT_SLACK, (
        "подъём отвечает МЕСТОМ, с которого пошёл показ, а не согласием"
    )
    assert loads[-1] == 148.940 + ChromecastReceiver.CUT_SLACK, (
        "третья смерть - перешагнут кусок декодера, а не картинки"
    )
    assert "skipping it" in capsys.readouterr().out, "решение сказано вслух"


def test_deaths_are_counted_where_the_show_died_and_not_where_the_jump_aims() -> None:
    """Подросший между смертями кадр обязан попадать в ТОТ ЖЕ счётчик.

    Замер на «Моане» 2016: за сеанс позиция подросла со 125.4 на 127.8 с - все четыре
    смерти легли в один и тот же кусок ``[124.583..137.095)``. Счёт по месту ПРИЦЕЛА
    (кадр + запас декодера) пересекает границу сетки на 127.095, то есть внутри этого
    самого дрейфа: смерти разъезжаются по двум счётчикам, ни один не добирает
    :attr:`~torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver.DEADLY_TRIES`,
    и перешагивание опаздывает на целый круг восстановления. Цель прыжка при этом остаётся у
    декодера.
    """
    receiver = _Free()
    loads = receiver.loads
    receiver.next_cut = _MOANA.after

    drift = (125.4, 127.2, 127.8)
    assert len({_MOANA.slot_at(at) for at in drift}) == 1, "замер: дрейф не выходит из куска"
    assert len({_MOANA.slot_at(at + receiver.profile.start_buffer) for at in drift}) == 2, (
        "и ровно на этом дрейфе прицел меняет кусок - иначе тест ничего не сторожит"
    )

    for at in drift:
        assert receiver.replay(at) > 0.0

    assert loads[:2] == [125.4, 127.2], "первые смерти возвращают человека туда, где он смотрел"
    assert loads[-1] == 148.940 + ChromecastReceiver.CUT_SLACK, (
        "третья смерть на том же куске перешагивает его, а не начинает счёт заново"
    )


class _Reported:
    """MEDIA_STATUS, как его отдаёт живой приёмник: позиция, состояние, длительность."""

    def __init__(self, pos: float, state: str = "PLAYING") -> None:
        self.current_time = pos
        self.player_state = state
        self.idle_reason = None
        self.duration = 5977.0
        self.player_is_playing = state in {"PLAYING", "BUFFERING"}


def test_the_peak_follows_the_viewer_back_after_a_rewind() -> None:
    """После перемотки назад нудж обязан целиться туда, где человек СЕЙЧАС.

    Замерено на живом Q70D дважды подряд: откат с 31:31 на 10:00, показ шёл
    чисто 18 с, потом ребуфер — и сторож выкинул фильм обратно на 31:31, в место, откуда
    зритель только что ушёл. Причина — пройденный максимум ``_peak``, который никогда не
    опускался: прыгаем мы только вперёд, поэтому уехавшая назад позиция может значить
    ровно одно — перемотку человека, и максимум обязан пойти за ним.
    """

    class _Scripted(_Wired):
        """Приёмник, чьи ответы заданы лентой замера, а не сетью."""

        def __init__(self, device: Any, script: list[_Reported]) -> None:
            super().__init__(device)
            self.script = script

        def _status(self) -> Any:
            return self.script.pop(0)

    jumps: list[float] = []
    stall = [_Reported(619.0, "BUFFERING")] * 2
    receiver = _Scripted(_FakeDevice(jumps), [_Reported(1891.0), _Reported(600.0), *stall])

    receiver.position(front=1951.0)  # шли на 31:31
    receiver.position(front=600.0)  # пульт: откат на 10:00
    assert receiver._peak == 600.0, "максимум пошёл за человеком, а не остался на 31:31"

    receiver.position(front=688.0)  # встали на 10:19 при готовой упаковке впереди
    receiver._stall_since -= CAUTIOUS.stall_seconds
    receiver.position(front=688.0)

    assert jumps == [619.0 + CAUTIOUS.stall_skip], (
        "нудж целится на кусок вперёд от текущего места, а не назад в покинутое"
    )


def test_a_zero_from_a_live_receiver_never_throws_the_show_back_to_the_beginning() -> None:
    """Приёмник отдал ноль, не назвавшись мёртвым, - и это не перемотка в начало.

    Замер на живом Q70D («Отряд самоубийц»): картинка была и стояла на 34.3 с, приёмник
    ответил нулём при живом состоянии, ноль сошёл за перемотку - максимум ушёл за ним, а
    от нуля прицелился сторож подвиса. В ленте это `seek 34.3 → 0.0,
    why=«сторож перебил нуджем»`, а зрителю - фильм, начавшийся сначала на 86-й секунде.
    """

    class _Scripted(_Reporting):
        """Приёмник, чьи ответы заданы лентой замера, а не сетью."""

        def __init__(self, device: Any, script: list[_Reported]) -> None:
            super().__init__(device)
            self.script = script

        def _status(self) -> Any:
            return self.script.pop(0) if len(self.script) > 1 else self.script[0]

    jumps: list[float] = []
    device = _FakeDevice(jumps)
    lost = _Reported(0.0, "BUFFERING")
    receiver = _Scripted(device, [_Reported(34.3), lost])
    receiver.device.status = lost

    receiver.position(front=94.3)  # картинка стояла на 34.3 с
    assert receiver._shown == 34.3, "кадр на экране запомнен"

    receiver.position(front=94.3)  # приёмник отдал ноль, живым себя называть не перестав
    assert receiver._peak == 34.3, "ноль живого приёмника местом показа не является"

    receiver._stall_since -= CAUTIOUS.stall_seconds
    receiver.position(front=94.3)

    assert jumps == [34.3 + CAUTIOUS.stall_skip], (
        "сторож толкает показ вперёд от увиденного кадра, а не отсчитывает от нуля"
    )
    assert min(jumps) > receiver._shown, "назад от увиденного кадра сторож не прыгает"


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


def _watched(gone: _Gone) -> _Reporting:
    """Приёмник поверх ушедшего устройства: и статус, и прыжки берутся у него."""
    return _Reporting(gone)


def test_a_blind_ladder_of_nudges_gives_up_instead_of_walking_the_movie() -> None:
    """Лестница нуджей без единого показанного кадра обязана кончиться - и передать
    показ воскрешению.

    Замер: за 780 с показа сторож сработал 24 раза, и 12 из них были одной лестницей
    подряд, без единого ``PLAYING`` между прыжками. Это не залипший кусок, а ушедший
    приёмник: прыжки его не лечат, а только шагают по фильму - те 12 нуджей увели
    указатель на 96 с впустую, и каждый стоил 8 с неподвижной картинки и до 8 с плёнки.
    """
    gone = _Gone(84.0)
    receiver = _watched(gone)

    result = receiver.position(front=1e6)
    for _ in range(30):  # минута показа при опросе раз в 2 с
        receiver._stall_since -= CAUTIOUS.stall_seconds
        result = receiver.position(front=1e6)
        if not result.playing:
            break

    limit = CAUTIOUS.blind_nudges
    assert len(gone.jumps) == limit, "лестница не остановилась - сторож шагает по фильму"
    assert gone.jumps == [84.0 + 8.0 * step for step in range(1, limit + 1)]
    assert not result.playing, "показ живым больше не считается - эстафета воскрешению"
    assert result.state == "BUFFERING", "состояние приёмника отдаём как есть, без вранья"
    assert gone.jumps[-1] - 84.0 == 8.0 * limit, "по фильму прошагано ровно на лестницу"


def test_a_single_nudge_still_pulls_the_receiver_out() -> None:
    """Штатный случай - подвис, вылеченный ОДНИМ нуджем, - счётчик лестницы не трогает.

    Пять разных подвисов за показ, каждый вылечен одним прыжком: показ всё это время
    живой, сторож всё это время на месте. Обнуляет счёт именно показанный кадр.
    """
    gone = _Gone(84.0)
    receiver = _watched(gone)

    for _ in range(5):
        gone.freeze()
        receiver.position(front=1e6)  # первый неподвижный тик - ещё не зависание
        receiver._stall_since -= CAUTIOUS.stall_seconds
        assert receiver.position(front=1e6).playing, "одиночный нудж показ не хоронит"
        gone.show(gone.status.current_time + 2.0)  # прыжок помог: кадр на экране
        assert receiver.position(front=1e6).state == "PLAYING"

    assert len(gone.jumps) == 5, "сторож остался на месте - лечить подвисы больше некому"
    assert receiver._blind == 0 and not receiver._gone


#: Сетка живого сеанса 11-08-2026 вокруг места, где показ встал: границы взяты у него же.
_TORN = Grid((0.0, 40.0, 80.0, 100.0, 118.7, 133.0), 5977.0, True)


def test_the_film_a_nudge_stepped_over_is_named_to_the_viewer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Прыжок сторожа стоит зрителю плёнки, и цену обязан назвать показ, а не догадка.

    Замер на живом Q70D 11-08-2026 (сеанс 1786444563-199339.1): показ встал на 103.6 с,
    сторож прыгнул за границу куска на 119.2 с - и 15.6 с фильма человек не увидел и не
    услышал. Строки об этом не было ни одной: у экрана слышно пропавший звук и не понять,
    файл это или техника. Размен «кусок мимо вместо смерти показа» правильный, но
    молчать о нём - то же самое подменённое кино, только тише.

    Цена считается ОТ КАДРА, на котором остался зритель, и ДО кадра, на котором показ
    ожил: прицел сторожа тут не число - приёмник вправе приземлиться и не туда.
    """
    gone = _Gone(103.6)
    receiver = _watched(gone)
    receiver.next_cut = _TORN.after
    assert _TORN.after(103.6) == 118.7, "замер: кусок зрителя кончается ровно здесь"

    receiver.position(front=1e6)  # первый неподвижный тик - ещё не зависание
    receiver._stall_since -= CAUTIOUS.stall_seconds
    receiver.position(front=1e6)
    assert gone.jumps == [118.7 + ChromecastReceiver.CUT_SLACK], "прыжок ушёл за кусок"
    assert capsys.readouterr().out == "", "в момент прыжка называть ещё нечего"

    gone.show(119.2)  # приёмник ожил ровно там, куда прыгнули
    assert receiver.position(front=1e6).state == "PLAYING"
    said = capsys.readouterr().out
    assert "skipped 16 s of film" in said, f"пропуск не назван числом: {said!r}"
    assert said.count("\n") == 1, f"одна честная строка, а не простыня: {said!r}"

    gone.show(121.2)
    receiver.position(front=1e6)
    assert capsys.readouterr().out == "", "об одном пропуске говорят один раз"


def test_a_show_raised_from_the_last_shown_frame_reports_no_gap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Подъём с кадра зрителя плёнки не стоил - и придумывать пропуск нельзя.

    Лестница нуджей уводит указатель по фильму, ничего при этом не показывая, и после неё
    показ поднимают с ПОСЛЕДНЕГО ПОКАЗАННОГО кадра, а не с места, куда уехал указатель.
    Плёнки такой круг не съедает ни секунды, и назвать его пропуском значило бы напугать
    зрителя потерей, которой не было. Счёт снимает сам подъём - потому что ровно он и
    знает, что вернул человека туда, где тот остался.

    ⚠️ По :attr:`~torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver._gone`
    этот счёт снимать нельзя, и тест сторожит именно подъём: ушедший приёмник иногда оживает сам, на
    том месте, куда его увела лестница, - и вот там пропуск настоящий.
    """

    class _Raised(_Reporting):
        """Ушедший приёмник, у которого подъём проходит: сеть тут не при чём."""

        def _restart_app(self) -> None:
            return None

        def _load(self, at: float = 0.0, paused: bool = False) -> None:
            return None

        def _free(self) -> bool:
            return True

        def _settle(self, budget: float) -> bool:
            return True

    gone = _Gone(103.6)
    receiver = _Raised(gone)

    receiver.position(front=1e6)
    for _ in range(30):  # минута показа при опросе раз в 2 с
        receiver._stall_since -= CAUTIOUS.stall_seconds
        if not receiver.position(front=1e6).playing:
            break
    assert receiver._gone, "лестница кончилась - эстафета воскрешению"
    assert gone.jumps[-1] > 103.6 + 8.0, "указатель уехал по фильму - было бы что назвать"
    capsys.readouterr()

    assert receiver.replay(103.6) == 103.6, "поднимаем с кадра, на котором остался зритель"
    gone.show(110.0)  # показ пошёл и идёт
    assert receiver.position(front=1e6).state == "PLAYING"
    assert capsys.readouterr().out == "", "потери не было - и говорить о ней не о чем"


def test_the_revival_names_the_place_the_show_actually_came_back_from(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """«Показ поднят с 1:43» на месте, с которого показ НЕ пошёл, - это то же враньё.

    Кусок, на котором показ уже умирал, приёмнику больше не отдаётся
    (:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver._past_deadly`),
    и подъём уезжает за него - на живом замере 11-08-2026 это 15.6 с фильма. Пока подъём отвечал
    «да/нет», строку о нём печатал тот, кто ПРОСИЛ, - и печатал ровно поверх честной строки о
    перешагнутом куске. Двух мнений о том, откуда идёт фильм, у зрителя быть не должно.
    """
    from torrcast.usecases.revive_playback._revival import _Revival

    class _Stepping:
        """Приёмник, который поднял показ ЗА куском, а не там, где его просили."""

        def play(self, url: str, title: str = "", at: float = 0.0) -> None: ...

        def stop(self, quit_app: bool = False) -> None: ...

        def position(self, front: float = 0.0) -> Position:
            return Position(119.2, 7200.0, True, "PLAYING")

        def replay(self, at: float) -> float:
            return 119.2

    revival = _Revival(clock=_Ticker(), drop=0.0, pause=0.0)
    revival.dropped = True  # темноту устроил приёмник: ждать источник тут нечего

    assert revival.resurrect(_Stepping(), _feed_with_segments(tmp_path), None, 103.6) is True
    said = capsys.readouterr().out
    assert "показ поднят с 0:01:59" in said, f"названо не то место: {said!r}"
    assert "показ поднят с 0:01:43" not in said, "строка называет место, где показа нет"


def test_only_the_cosmetic_pychromecast_line_is_hushed(caplog: pytest.LogCaptureFixture) -> None:
    """Гасим РОВНО одну строку чужой библиотеки, а настоящие её жалобы доходят.

    Строка про «не смог определить тип устройства» печатается на каждом подключении и
    ничего не значит: pychromecast спрашивает страницу сведений по https на 8443,
    которого у телевизора нет, ловит отказ тут же и подставляет тип по умолчанию.
    ``port=8009`` в её тексте - распечатка списка сервисов, а не отказавший порт; на этом
    уже строилась ложная гипотеза «телевизор выпадает по 8009».
    """

    hush_cosmetic_noise()
    hush_cosmetic_noise()  # второй вызов второго фильтра не вешает
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


def _receiver_on(cast: _FakeCast, url: str = "http://10.0.0.10:8443/index.m3u8") -> _Silenced:
    """Приёмник поверх подставного устройства: LOAD записывается, свобода экрана живая."""
    receiver = _Silenced()
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
    clip: str, tls: tuple[str, str], tmp_path: Path
) -> None:
    """Стык серий и конец показа — для приёмника разные события.

    Проверяется вся проводка целиком, от состояния до приёмника: сторож дошёл до порога
    95 %, показ кончился — и только запись состояния решает, закрывать ли приложение.
    Серия не последняя — оно достаётся следующей; последняя — гаснет, как у фильма.
    """
    from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver

    quits: list[bool] = []

    class _Recorder(MockReceiver):
        """Заглушка, помнящая, закрывали ли ей приложение на выходе."""

        def stop(self, quit_app: bool = False) -> None:
            quits.append(quit_app)
            super().stop()

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
        _play(
            config,
            clip,
            0,
            "тест",
            _Clock(),
            watch=_Watch(key=key, entry=entry, every=0.0),
            receiver=_Recorder(),
        )

    run(episode=1)
    assert quits == [False], "серия досмотрена, впереди s1e2 - приложение не трогаем"

    run(episode=2)
    assert quits == [False, True], "последняя серия - показ окончен, приложение закрываем"


def test_a_finished_movie_hands_nothing_over(tmp_path: Path) -> None:
    """Конец фильма (титры) и `cast stop` посреди — оба раза передавать показ некому,
    значит приложение приёмника закрывается.
    """

    key = "movie:ролик:2026"
    entry = Entry(title="ролик", magnet="magnet:?xt=1", pos=95.0, dur=100.0)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    assert not _handover(watch), "`cast stop`: сторож не досматривал - передавать нечего"

    watch.see(95.0)  # приёмник досчитал до титров
    watch.close()  # конец сеанса на титрах: фильму это «досмотрено», а не следующая серия
    assert watch.done and not _handover(watch), "титры кончились - закрываем приложение"


def test_the_series_hands_over_at_the_end_of_the_stream_and_not_a_moment_earlier(
    tmp_path: Path,
) -> None:
    """🔴 Стык серий живёт на конце потока, а не на доле длительности.

    Серия обязана доиграть до самого конца: пока приёмник считает, показ никуда не уводят
    - ни на 95 %, ни за секунду до конца. Следующую серию записывает конец сеанса, и
    записывает всегда: потерять переход страшнее, чем потерять хвост.
    """
    key = "tv:киберпанк:2022"
    entry = Entry(
        title="Киберпанк",
        magnet="magnet:?xt=1",
        kind="tv",
        season=1,
        episode=2,
        episodes=[[1, 2, 5], [1, 3, 6]],
        dur=2700.0,
    )
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    watch.see(2698.6)  # 1.4 с до конца - серия ещё играет
    held = State.load().get(key)
    assert held is not None and (held.season, held.episode) == (1, 2), (
        "пока приёмник считает, показ остаётся на этой серии"
    )

    watch.close()  # приёмник доиграл файл, сеанс кончился

    saved = State.load().get(key)
    assert saved is not None
    assert (saved.season, saved.episode) == (1, 3), "в состоянии следующая серия раздачи"
    assert saved.file_idx == 6 and saved.pos == 0 and not saved.done


def test_a_movie_finished_by_the_receiver_is_always_marked_watched(tmp_path: Path) -> None:
    """Пометка «досмотрено» у фильма приезжает всегда, даже когда последний опрос лёг за
    полторы секунды до конца: иначе закладка звала бы продолжить с титров, а прогретое
    осталось бы лежать на диске навсегда.
    """
    key = "movie:ролик:2026"
    entry = Entry(title="ролик", magnet="magnet:?xt=1", dur=100.0)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    watch.see(98.6)
    watch.close()

    assert watch.done
    saved = State.load().get(key)
    assert saved is not None and saved.done and saved.pos == 0


def test_a_show_cut_in_the_middle_is_not_watched_and_keeps_its_bookmark(tmp_path: Path) -> None:
    """Оборванный посреди картины показ досмотренным не становится ни от какого конца
    сеанса: закладка остаётся на месте, и `cast` продолжит с неё.
    """
    key = "movie:ролик:2026"
    entry = Entry(title="ролик", magnet="magnet:?xt=1", dur=100.0)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    watch.see(41.0)
    watch.close()

    assert not watch.done
    saved = State.load().get(key)
    assert saved is not None and not saved.done and saved.pos == 41.0 and saved.resumable


def test_a_closed_show_never_starts_ffmpeg_again(tmp_path: Path) -> None:
    """Показ окончен — поток раздачи, проснувшийся в segment(), не поднимает упаковку.

    На стыке серий следующая серия уже чистит каталог и пакует своё; осиротевший ffmpeg
    прошлой серии выкладывал бы туда её сегменты под теми же именами.
    """
    asked: list[int] = []

    class _Noting(Feed):
        """Раздача, которая запоминает просьбы поднять упаковку, а не исполняет их."""

        def restart(self, slot: int) -> None:
            asked.append(slot)

    feed = _feed_with_segments(tmp_path, kind=_Noting)

    feed.stop()

    assert feed.segment(70) is None and asked == [], "после stop упаковку не поднимаем"


def test_the_cli_never_kills_a_show_that_is_still_inside_the_units_budget(
    tmp_path: Path,
) -> None:
    """Ожидание картинки согласовано с бюджетами юнита, а не взято «побольше».

    CLI ждёт картинку и по своему таймауту гасит показ. Пока он ждал 120 с, а юнит имел
    право потратить на метаданные, ffprobe, карту, пробный прогон и терпение к молчащему
    приёмнику куда больше, `cast` убивал показ, который вот-вот начался бы. Согласие
    здесь одно: ждать не меньше суммы потолков всех фаз, которые юнит проходит до
    первого ``PLAYING``.
    """
    from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
    from torrcast.domain.hls_wait import KEYS_WAIT, PILOT_TIMEOUT

    phases = (
        WORKER_META  # метаданные раздачи по DHT
        + WORKER_DUR  # ffprobe длительности серии
        + KEYS_WAIT  # чужая карта опорных кадров снимается прямо сейчас
        + PILOT_TIMEOUT  # пробный прогон упаковки в один кадр
        + ChromecastReceiver.START_TIMEOUT  # молчаливый IDLE после LOAD
    )
    assert phases <= START_BUDGET, "CLI сдаётся раньше, чем юнит исчерпал своё право"

    clock, unit = FakeClock(), FakeShowUnit(alive=True)

    class _Mute:
        def phase(self, text: str) -> None: ...

    with pytest.raises(InfraError):
        _await_playing(
            Config(hls_dir=str(tmp_path)),
            _Mute(),  # type: ignore[arg-type]
            clock=clock,
            unit=unit,
        )

    assert unit.stops == [1] and clock.monotonic() >= phases, "показ погашен внутри бюджета юнита"


class _Service:
    """Служба раздач глазами показа: жива ли, что у неё в списке и что она знает о файлах.

    Ровно те три вопроса, из которых складывается ответ «виноват источник»
    (:meth:`torrcast.adapters.stream_probe.supply.Supply.check`), плюс счётчик добавлений: возврат
    раздачи магнитом обязан быть идемпотентным и не трогать ничего, кроме нашего хэша.
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

    def status(self, torrent_hash: str) -> dict[str, object]:
        if not self.up:
            raise InfraError("TorrServer не отвечает")
        files = [{"id": 0, "path": "film.mkv", "length": 1_000_000_000}] if self._files else []
        return {"file_stats": files}

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
    from torrcast.adapters.stream_probe.supply import Supply

    return Supply(service, torrent_hash=MAGNET_HASH, magnet=MAGNET)


def _events(directory: Path) -> list[dict[str, Any]]:
    from torrcast.adapters.filesystem.trace_journal.shutdown import shutdown

    shutdown()
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("trace-*.jsonl")):
        for raw in path.read_text("utf-8").splitlines():
            rows.append(json.loads(raw))
    return rows


def test_a_dead_source_is_named_instead_of_blaming_the_receiver(
    tmp_path: Path, journal: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Показ гаснет при мёртвом источнике - и виноватым называется ИСТОЧНИК.

    Замер на живом стенде: перезапуск службы раздач посреди показа кончал показ за
    3.5-12 с, человек 14 с не видел ни строки, а потом получал «приёмник не досмотрел
    поток». Своих признаков у показа тут нет ни одного: трёхсекундный обрыв не взводит
    ни счёт оборванных прогонов, ни часы молчания, и :attr:`Feed.offline` пуст. Поэтому
    прежде, чем признать показ погасшим, спрашивается сам источник - и его ответ уходит
    одной и той же строкой и человеку, и в недельный след.
    """

    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    service = _Service(up=False)

    _hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00 (TorrServer не отвечает)" in printed, (
        "человеку сказано про источник, а не про приёмник"
    )
    rows = _events(journal)
    dark = next(r for r in rows if r["event"] == "dark")
    offline = next(r for r in rows if r["event"] == "offline")
    assert dark["why"] == "TorrServer не отвечает" == offline["why"], "след и строка совпадают"
    assert offline["asked"] is True, "причина взята у самого источника, а не угадана"
    assert receiver.replays == [], "пока источник лежит, терпение приёмника не жжём"


def test_the_returning_source_gets_the_torrent_back_by_magnet(
    tmp_path: Path, journal: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Служба вернулась - раздачу добавляем МАГНИТОМ, и только потом поднимаем показ.

    Если записи раздачи у службы нет, а в URL потока едет только хэш, попросив по нему
    поток, мы получили бы раздачу без
    трекеров - замерено, 25 с и ноль байт, пиры только по DHT. Трекеры живут в магните из
    записи картины, и возвращает их этот вызов - ровно один, идемпотентный и только по
    нашему хэшу.
    """

    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    warmer.warmed = 0.0  # прогрева нет: возврат показа держится только на источнике
    service = _Service(up=False)

    def restore(_seconds: float) -> None:
        service.up = clock.now - 1000.0 >= 30.0
        if service.up:
            (feed.out / segment_name(feed.grid.slot_at(1200.0))).write_bytes(b"ready")

    clock.ticks.append(restore)
    service._listed = service._files = False  # перезапуск: своей раздачи она не помнит

    _hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    assert service.added == [MAGNET], "раздачу вернули магнитом ровно один раз"
    assert service.dropped == [], "чужих раздач и своей же не сносим - только добавляем"
    assert receiver.replays == [1200.0], "показ поднят с того места, где смотрели"
    printed = capsys.readouterr().out
    assert "источник вернулся - раздачу добавил магнитом заново" in printed
    rows = _events(journal)
    back = next(r for r in rows if r["event"] == "resupply")
    assert back["torrent"] == MAGNET_HASH and back["ok"] is True


def test_a_torrent_left_as_a_bare_hash_is_a_source_failure() -> None:
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


def test_a_healthy_source_is_never_blamed_and_never_re_added() -> None:
    """Источник в порядке - он и молчит: ни строки обвинения, ни лишнего добавления."""
    service = _Service()
    supply = _supply(service)

    assert supply.check() == "" and not supply.restored
    assert service.added == [] and service.dropped == []


def test_a_dead_source_does_not_kill_the_show_when_packing_gives_up(
    tmp_path: Path, journal: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Упаковка сдалась, а виноват источник - показ не умирает, а ждёт его возврата.

    Три оборванных подряд прогона значат «показывать нечего» только при живом источнике.
    Служба раздач, которую перезапустили, рвёт вход точно так же, и старый показ хоронил
    себя строкой «упаковка оборвалась» - про наш ffmpeg, а не про причину.
    """

    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    feed.fatal = "ffmpeg сдался: Input/output error"
    service = _Service(up=False)

    _hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    printed = capsys.readouterr().out
    assert "источник не читается (TorrServer не отвечает) - жду его возврата" in printed
    assert "упаковка оборвалась" not in printed, "показ не хоронит себя чужой виной"
    assert feed.offline == "TorrServer не отвечает", "приговор упаковке снят, показ ждёт"
    rows = _events(journal)
    assert [r["asked"] for r in rows if r["event"] == "offline"] == [True]


def test_a_packing_failure_on_a_healthy_source_still_ends_the_show(tmp_path: Path) -> None:
    """Источник в порядке, а упаковка сдалась - это по-прежнему конец показа с ошибкой."""

    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    feed.fatal = "ffmpeg сдался: Invalid data found"
    service = _Service()

    with pytest.raises(InfraError, match="упаковка оборвалась"):
        _hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]


def test_the_source_is_never_asked_while_the_picture_is_alive(tmp_path: Path) -> None:
    """Пока идёт картинка, источник не спрашивают ни разу.

    Ограждение горячего пути: показ не имеет права ждать ни журнал, ни лишний запрос -
    вопросы источнику появляются только там, где показ уже кончается. Здесь показ идёт
    ровно так, как ему положено: приёмник играет, упаковка жива, - и ни один запрос к
    источнику не уходит.
    """

    class _Counted(Supply):
        """Источник, который считает, сколько раз его спросили."""

        asked = 0

        def check(self) -> str:
            self.asked += 1
            return ""

    feed = _feed_with_segments(tmp_path)
    supply = _Counted(_Service(), torrent_hash=MAGNET_HASH, magnet=MAGNET)
    receiver = _FakeReceiver([(200.0, "PLAYING"), (210.0, "PLAYING"), (220.0, "PLAYING")])

    _hold(receiver, feed, None, None, supply, clock=FakeClock(1000.0))

    assert supply.asked == 0, "живой показ источник не спрашивает"


def test_a_show_that_never_started_still_names_the_dead_source() -> None:
    """Показ, не сдвинувшийся с нуля, кончается строкой про ИСТОЧНИК, а не про приёмник.

    Сюда приходит самый обидный случай: картинка так и не поехала, поднимать нечего и
    неоткуда (:class:`torrcast.usecases.revive_playback._revival._Revival` без позиции не работает),
    - и человек получал «приёмник не досмотрел поток» при живом приёмнике и мёртвой службе раздач.
    Спросить источник тут стоит тех же двух запросов, а показ уже кончился: горячего пути нет.
    """

    service = _Service(up=False)
    supply = _supply(service)

    with pytest.raises(InfraError, match="источник не читается \\(TorrServer не отвечает\\)"):
        _blame_the_end(supply, clock=FakeClock())


def test_a_show_that_never_started_blames_the_receiver_when_the_source_is_fine() -> None:
    """Источник в порядке - строка остаётся прежней, и это правильно."""

    with pytest.raises(InfraError, match="приёмник не досмотрел поток"):
        _blame_the_end(_supply(_Service()), clock=FakeClock())


def test_a_source_that_came_back_by_itself_is_still_the_one_to_blame(
    tmp_path: Path, journal: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Служба поднялась за три секунды - и всё равно виновата она, а не приёмник.

    Замер на стенде: перезапуск службы раздач стоит 3.0-3.1 с недоступности, а терпение
    приёмника - минуты. К мгновению, когда показ признан погасшим, служба уже отвечает, и
    вопрос «сейчас всё хорошо?» сам по себе оправдал бы её. Доказательство аварии - в том,
    что раздачу пришлось возвращать магнитом: без падения службы её никто не терял бы.
    """

    clock, feed, warmer, receiver = _dark(tmp_path, offline="")
    service = _Service(listed=False, files=False)  # служба уже поднялась, но список пуст

    _hold(receiver, feed, None, warmer, _supply(service), clock=clock)  # type: ignore[arg-type]

    printed = capsys.readouterr().out
    assert "показ погас на 0:20:00 (TorrServer перезапускался - раздачу вернул магнитом)" in printed
    assert service.added == [MAGNET], "раздача вернулась магнитом, а не голым хэшем"
    rows = _events(journal)
    assert next(r for r in rows if r["event"] == "dark")["why"] == (
        "TorrServer перезапускался - раздачу вернул магнитом"
    )


def test_the_source_is_asked_more_than_once_before_it_is_believed() -> None:
    """Один вопрос источнику - мало: умирающая служба отвечает как живая.

    Замер на живой службе (05:37:48.3 - 05:37:51.5): все три секунды своей остановки
    TorrServer отвечал на ``/echo`` и отдавал список раздач, а показ умирает как раз
    внутри этого окна. Здесь служба тоже «здорова» на первых вопросах и теряет раздачу
    на третьем - и виноватым всё равно называется источник.
    """

    class _SlowDeath(_Service):
        """Служба, умирающая на третьем вопросе: первые два она отвечает как живая."""

        asked = 0

        def listed(self, torrent_hash: str) -> bool:
            self.asked += 1
            if self.asked >= 3:
                self._listed = False
            return super().listed(torrent_hash)

    service = _SlowDeath()

    with pytest.raises(InfraError, match="источник не читается"):
        _blame_the_end(_supply(service), clock=FakeClock())

    assert service.asked >= 3, "источник спрошен несколько раз, а не единожды"
    assert service.added == [MAGNET], "заметив пропажу, раздачу вернули магнитом"


def test_the_picture_is_proved_by_a_moving_pointer_not_by_the_word_playing(
    tmp_path: Path,
) -> None:
    """``PLAYING`` при стоящем указателе - это ещё не картинка, и флажок ему не полагается.

    🔴 Замер на живом Q70D (заход в тяжёлое место, сплошной перекод): приёмник отвечает
    ``PLAYING`` на 8.2-й секунде, а указатель стоит на месте захода ещё 6.0 с - до тех
    пор, пока показ не выложил ВТОРОЙ кусок. То есть каждое «старт NN с» было занижено
    на 5-6 с ровно там, где человеку хуже всего. Здесь показ дожидается сдвига указателя.
    """
    from torrcast.adapters.stream_pack.playing_flag import playing_flag

    feed = _feed_with_segments(tmp_path)
    # Приёмник говорит «играю», не двигая указатель, и только потом трогается с места.
    stuck = _FakeReceiver([(300.0, "PLAYING"), (300.0, "PLAYING"), (0.0, "IDLE")])

    _hold(stuck, feed, clock=FakeClock(1000.0))

    assert not playing_flag(feed.out).exists(), "указатель стоял - картинки не было"

    feed = _feed_with_segments(tmp_path)
    moved = _FakeReceiver([(300.0, "PLAYING"), (300.5, "PLAYING"), (0.0, "IDLE")])

    _hold(moved, feed, clock=FakeClock(1000.0))

    assert playing_flag(feed.out).exists(), "указатель пошёл - вот это и есть картинка"


def test_the_mock_waits_for_as_much_film_as_the_receiver_gathers_before_the_first_frame() -> None:
    """Заглушка не показывает кадр раньше, чем показ набрал запас живого приёмника.

    🔴 Замер на живом Q70D (:attr:`torrcast.domain.profile.Profile.start_buffer`): на сетке по 8 с
    указатель тронулся только со ВТОРЫМ куском (16 с фильма), на сетке по 2.5 с - с
    четвёртым (10 с), а на третьем (7.5 с) ещё стоял. Заглушка объявляла картинку по
    первому же сдвигу своего декодера, то есть сухой прогон был бодрее живого ТВ на те
    самые секунды, из-за которых старт и меряют.
    """
    from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
    from torrcast.domain.position import Position

    assert CAUTIOUS.start_buffer == 10.0, "замер: столько фильма Q70D копит до первого кадра"

    # Декодера тут нет вовсе, поэтому фильм не кончается ничем: проверяется запас, а не титры.
    mock = MockReceiver()
    mock.decoder.pos = Position(300.0, 0.0, True)

    # Один кусок по 8 с впереди - живой приёмник тут ещё копит и кадра не показывает.
    assert mock.position(front=308.0).state == "BUFFERING", "8 с фильма приёмнику мало"
    mock.decoder.pos = Position(300.5, 0.0, True)
    # Второй кусок пришёл - запас перевалил за десять секунд, вот теперь картинка.
    assert mock.position(front=316.0).state == "PLAYING", "16 с - приёмник трогается"
    mock.decoder.pos = Position(301.0, 0.0, True)
    assert mock.position(front=303.0).state == "PLAYING", "копит он один раз, на заходе"


def test_the_mock_tells_the_credits_from_a_source_that_died_under_the_show() -> None:
    """Заглушка отличает конец фильма от смерти источника, а не зовёт титрами любой ноль.

    🔴 Замер TC-314: источник пропал под показом, ffmpeg закрыл вход нулём на 0:04:42 из
    2:46:55, и сухой прогон записал это «фильм доигран» - в журнале ``экран: 0:04:42`` с
    пустым состоянием. Пока это считалось титрами, ни один замер досмотра заглушкой не
    доказывался: авария на пятой минуте читалась успехом. Пустой манифест - тот же случай:
    длины нет, и звать титрами тут нечего.
    """
    from torrcast.domain.watch_ratios import ENDING_RATIO

    whole = 10015.0  # 2:46:55 - длина того самого фильма

    died = MockReceiver()
    died.decoder.proc = FakeProc(0)  # type: ignore[assignment]
    died.report.duration = whole
    died.decoder.pos = Position(282.0, whole, False)  # 0:04:42, декодер уже вышел

    assert not died.screen.over(), "ноль на пятой минуте - это оборванный источник, а не титры"
    seen = died.position()
    assert (seen.state, seen.playing) == ("BUFFERING", True), (
        "смерть источника уходит в терпение приёмника, как оборванная картинка на ТВ"
    )

    ended = MockReceiver()
    ended.decoder.proc = FakeProc(0)  # type: ignore[assignment]
    ended.report.duration = whole
    ended.decoder.pos = Position(whole * ENDING_RATIO, whole, False)

    assert ended.screen.over(), "вышел нулём за порогом досмотра - вот это титры"
    assert ended.position().state == "", "титры показ узнаёт по пустому состоянию"

    blind = MockReceiver()
    blind.decoder.proc = FakeProc(0)  # type: ignore[assignment]
    blind.decoder.pos = Position(282.0, 0.0, False)
    assert not blind.screen.over(), "в манифесте пусто - это смерть источника, а не титры"
    assert blind.position().state == "BUFFERING", "неизвестная длина уходит в терпение"


def test_the_diagnostic_remote_steers_the_mock_receiver(remote: Path) -> None:
    """Пульт (``TORRCAST_CTL``) доезжает до заглушки: пауза, снятие паузы, перемотка.

    🔴 Заглушка не реализовывала ни одного из трёх методов, не проходила проверку «этим
    можно рулить» (:class:`torrcast.usecases.choice._ctl._Steerable`) - и команда пульта на сухом
    прогоне молча оставалась лежать файлом. То есть перемотку и паузу заглушкой проверить было нечем
    вовсе: «на mock перемотка работает» доказывалось ничем.

    Пауза тут не бутафория: декодер умолкает по-настоящему (упаковке на паузе класть
    некому), показ при этом жив и стоит ровно на своём месте, а снятая пауза продолжает
    его оттуда же.
    """

    mock = _Opening()
    assert isinstance(mock, _Steerable), "заглушкой обязано быть можно рулить"

    opens = mock.opens
    mock._url = "http://127.0.0.1:9/hls/index.m3u8"
    mock.decoder.proc = FakeProc()  # type: ignore[assignment]
    mock.decoder.pos = Position(600.0, 7200.0, True)
    mock.report.duration = 7200.0

    remote.write_text("pause", "utf-8")
    _ctl(mock)

    decoder = mock.decoder.proc
    assert decoder is not None and decoder.poll() == -15, (
        "декодер умолк - сегментов приёмник больше не берёт"
    )
    held = mock.position()
    assert (held.state, held.pos, held.playing) == ("PAUSED", 600.0, True), (
        "на паузе показ жив и стоит на месте, а не считается погасшим"
    )
    assert opens == [], "пауза - не LOAD"

    remote.write_text("play", "utf-8")
    _ctl(mock)

    assert opens == [600.0], "снятая пауза продолжает показ ровно с того места, где он стоял"
    assert not mock.screen.paused and mock.position().state != "PAUSED"

    remote.write_text("seek 1200.5", "utf-8")
    _ctl(mock)

    assert opens == [600.0, 1200.5], "перемотка доехала до заглушки тем же местом, что и на ТВ"


class _Silent:
    """Поток, которого нет: заглушку тут проверяют без её же фоновых читателей."""

    def start(self) -> None:
        pass

    def join(self, timeout: float | None = None) -> None:
        pass


def test_the_mock_never_rewinds_the_show_to_the_head_of_the_film() -> None:
    """Приёмник, посланный на 0:20:00, до первого слова декодера стоит ТАМ, а не в начале.

    🔴 Замер TC-350: на возобновлении показа заглушка отматывала позицию назад (в статусе
    0:00:52 → 0:00:09), и в состояние уходило место, где зритель не был. Закладку сухим
    прогоном проверить было нечем: продолжение с середины читалось как старт с нуля.
    Живой Q70D держит указатель ровно на месте захода, пока копит фильм до первого кадра.
    """

    class _Answered:
        """Раздача, отвечающая пустым манифестом: проверяется учёт места, а не сеть."""

        status_code = 200
        headers: Final = {"Access-Control-Allow-Origin": "*"}
        text = ""

        def get(self, url: str, timeout: float = 0.0) -> _Answered:
            return self

        def raise_for_status(self) -> None:
            return None

    mock = MockReceiver(
        spawn=lambda *args, **kwargs: FakeProc(),
        thread=lambda *args, **kwargs: _Silent(),
    )
    mock.fetch.session = lambda ca: _Answered()
    mock.play("http://127.0.0.1:9/hls/index.m3u8", at=1200.0)
    mock.report.duration = 7200.0

    seen = mock.position(front=1260.0)
    assert seen.pos == 1200.0, "показ продолжается с 0:20:00, а не с головы фильма"
    assert mock.position(front=1260.0).pos == 1200.0, "и на следующем опросе тоже"


def test_a_show_that_never_started_is_not_marked_watched(tmp_path: Path) -> None:
    """🔴 Показ, которого не было, досмотренным не становится - и закладку не теряет.

    Замер на живой приставке: фильм продолжали с 2:14:15 из 2:16:15, источник под показом
    умер, приёмник не взял LOAD ни разу («LOAD не взяли (IDLE)», два повтора). Позиция при
    этом стояла на закладке, то есть за щедрой долей конца, - и конец сеанса записывал
    «досмотрено: 2:16:15 из 2:16:15», не показав ни кадра. Заодно стиралось прогретое:
    человек терял и место, и диск, а вернуться ему было некуда.
    """
    key = "movie:матрица:1999"
    entry = Entry(title="Матрица", magnet="magnet:?xt=1", pos=8055.5, dur=8175.5)
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)

    watch.close()  # приёмник не назвал ни одной живой позиции

    assert not watch.done, "ни кадра не показали - досматривать было нечего"
    saved = State.load().get(key)
    assert saved is not None and not saved.done
    assert saved.pos == 8055.5 and saved.resumable, "закладка осталась на месте"


class _Stuck:
    """Приёмник, залипший на последнем куске: указатель стоит, а живым себя считает.

    Ровно так выглядит конец картины у приёмника, который не сказал о нём чисто: сессию
    он не закрывает, в IDLE не уходит, ``current_time`` не двигает. Счётчик опросов тут
    не украшение: без страховки показ висел бы на этом месте вечно, и тест не падал бы, а
    не кончался.
    """

    def __init__(self, at: float, limit: int = 200) -> None:
        self.at, self.limit, self.asked = at, limit, 0

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self, quit_app: bool = False) -> None:
        pass

    def position(self, front: float = 0.0) -> Any:
        from torrcast.domain.position import Position

        self.asked += 1
        if self.asked > self.limit:
            raise AssertionError("показ висит на залипшем приёмнике и сеанс не кончается")
        state = "PLAYING" if self.asked <= 2 else "BUFFERING"
        return Position(self.at, 0.0, True, state)


def test_a_receiver_frozen_on_the_last_chunk_still_hands_the_show_over(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 Страховка перехода: конец потока приёмник называет не всегда.

    Залипший на последнем куске рапортует BUFFERING и живым быть не перестаёт, а сторож
    подвиса на нём молчит по своему же правилу: впереди честно пусто, потому что картина
    кончилась, и неподвижность он читает как законное ожидание упаковки. Своего конца у
    такого сеанса нет вовсе - показ висел бы до утра, а следующая серия не начиналась бы.
    Терять тут нечего, кроме хвоста, а приобретается переход - он дороже.
    """

    key = "tv:киберпанк:2022"
    entry = Entry(
        title="Киберпанк",
        magnet=MAGNET,
        kind="tv",
        season=1,
        episode=2,
        episodes=[[1, 2, 5], [1, 3, 6]],
        pos=7100.0,
        dur=7200.0,
    )
    state = State()
    state.put(key, entry)
    state.save()
    watch = _Watch(key=key, entry=entry, every=0.0)
    clock = _Ticker()
    feed = _feed_with_segments(tmp_path)
    receiver = _Stuck(at=7100.0)

    ended = _hold(receiver, feed, watch, None, clock=clock)

    assert ended, "неподвижный конец - это конец, а не авария: винить упаковку не в чем"
    assert "считаю доигранным" in capsys.readouterr().out, "молча показ не кончают"
    watch.close()
    saved = State.load().get(key)
    assert saved is not None and (saved.season, saved.episode) == (1, 3), (
        "переход обязан случиться и на приёмнике, не сказавшем о конце"
    )
