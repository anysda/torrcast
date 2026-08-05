"""Цепочка показа целиком на синтетическом ролике: упаковка → раздача → mock-приёмник.

Живая приёмка §7.2 идёт на «Моане 2» (docs/stage2.md), а регрессию ловит этот тест:
он гоняет тот же код без торрента и укладывается в секунды.

Здесь же живёт единственная проверка §6.1 SPEC-v2, которую нельзя сделать на бумаге:
кусок под именем ``vN`` обязан быть одним и тем же местом фильма, с какого бы места ни
начали паковать. Проверяется это настоящим ffmpeg на настоящем ролике — арифметикой
границ (tests/test_hls.py) доказывается только то, что мы его об этом попросили.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import CLIP_SECONDS, fake_packer
from torrcast import InfraError
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


def config_for(tmp_path: Path, tls: tuple[str, str], port: int) -> Config:
    """Конфиг показа как на стенде: http по голому IP (§5 SPEC-v2), приёмник — mock.

    ``tls`` тут остаётся ради второго прогона той же цепочки по https: транспорт —
    выключенная опция, но она обязана работать, и проверяется тем же тестом.

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
        hls_port=port,
        hls_readrate=0.0,  # приёмка идёт быстрее реального времени
        hls_keyframes=False,
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


def test_the_same_name_holds_the_same_piece_wherever_packing_started(
    clip: str, tmp_path: Path
) -> None:
    """§6.1 SPEC-v2 живьём: имя сегмента — это место в фильме, а не порядковый номер.

    Ровно это ломалось до 06-08-2026: сегментный муксер отсчитывал границы от первого
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
    """Источник — AC3 5.1; на выходе обязан быть AAC stereo, видео — тот же H.264 (§3, §9)."""
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
    """Сносить упаковку, как только она поднимется, — и так пока показ не сдастся.

    Ждём кусок в каталоге прогона, а не снаружи: наружу он попадёт только после
    :meth:`Packer.publish`, и к тому времени можно не успеть вклиниться.
    """
    out = Path(config.hls_dir)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if list(out.glob("**/v*.ts")):
            subprocess.run(["pkill", "-9", "-f", pattern], check=False)
        time.sleep(0.3)


def _alive(pattern: str) -> bool:
    done = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
    return bool(done.stdout.strip())


class _FakeReceiver:
    """Приёмник по сценарию: очередь состояний, как их отдаёт живой Q70D."""

    def __init__(self, script: list[tuple[float, str]]) -> None:
        self.script = script

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        pass

    def stop(self) -> None:
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

    Перемотку он больше не ловит вовсе — приёмник видит весь фильм и мотает сам (§2.1
    SPEC-v2), а раздача пакует то место, которое он попросил.
    """
    from torrcast import cli

    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    feed = _feed_with_segments(tmp_path)
    receiver = _FakeReceiver([(200.0, "PLAYING"), (0.0, "IDLE")])

    cli._hold(receiver, feed)

    edge = feed.grid.slot_at(160.0)
    left = sorted(int(path.name[1:-3]) for path in feed.out.glob("v*.ts"))
    assert left == list(range(edge, 60)), "позади показа держим окно, остальное — из RAM"


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
    сказал (§4 SPEC-v2). Снимать доказательство на каждом перезапуске значило бы врать.
    """
    feed = _feed_with_segments(tmp_path)
    mark_playing(feed.out)
    assert feed.packer is not None

    feed.packer.stop(keep_files=True)  # так гаснет упаковка между кусками фильма

    assert playing_flag(feed.out).exists(), "показ идёт — флажок на месте"
    assert sorted(feed.out.glob("v*.ts")), "упакованное перезапуск не выбрасывает"


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
    # Длительность занижена на сегмент — хвост HLS у клиента может отвалиться, а проверяем
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

    config = config_for(tmp_path, tls, 18465)
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
    """§6 SPEC-v2: неподвижный BUFFERING — это две разные беды, и лечатся они по-разному.

    Замерено на живом Q70D 05-08-2026: на 1:24 «Моаны» приёмник встал намертво при 60 с
    готовой упаковки впереди, сам не ожил ни разу и оживал только от нашего ``seek``. А
    ровно так же выглядит приёмник, который честно ждёт упаковку, — и вот его трогать
    нельзя: прыжок уведёт показ в неупакованное место и заставит паковать заново.
    """
    from torrcast.cast import ChromecastReceiver

    jumps: list[float] = []
    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice(jumps))
    receiver = ChromecastReceiver("192.168.100.102")
    receiver._peak = 84.0

    receiver._nudge(84.0, front=144.0)
    assert jumps == [], "первый неподвижный тик — ещё не зависание"

    receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
    receiver._nudge(84.0, front=88.0)
    assert jumps == [], "запаса впереди нет — приёмник ждёт нас, а не завис"

    receiver._nudge(84.0, front=144.0)
    assert jumps == [84.0 + ChromecastReceiver.STALL_SKIP], "еда на столе — расшевелить"
