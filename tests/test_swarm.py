"""Ранний отказ на мёртвом рое (TC-60).

Живой репорт: «cast cars» -> одна картина -> «дорожки... 40.0 с» -> «релиз не годится
(ffprobe не дождался потока)». Раздача с мёртвым роем метаданные отдаёт (они уже в
TorrServer), а содержимого не отдаёт вовсе, и весь :data:`PROBE_BUDGET` сгорал на ОДНОМ
молчащем релизе — при том что запасной уже грелся параллельно. Правило TC-39 («молчание
роя не жжёт попытку») тут не спасало: кандидат был один.

Признак жизни (:func:`swarm_pulse`) отличает молчащий рой от честно долгого заголовка
(«Моана 2» едет 17 с) и даёт оборвать ffprobe рано, не жгя весь бюджет.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import TYPE_CHECKING, Any, Literal, cast

import pytest

from tests.test_cli import _FakeTorrServer, _resolve, rel
from torrcast import InfraError, cli
from torrcast import stream as stream_mod
from torrcast.parse import Release
from torrcast.stream import Media, swarm_pulse

if TYPE_CHECKING:
    from pathlib import Path


def test_run_ffprobe_returns_the_moment_the_probe_exits() -> None:
    """Живой релиз не ждёт бюджета: как только ffprobe вышел, отдаём его вывод."""
    began = time.monotonic()
    out = stream_mod._run_ffprobe(["printf", "hello"], timeout=40.0, alive=lambda: True)
    assert out == "hello"
    assert time.monotonic() - began < 2.0


def test_run_ffprobe_bails_at_once_on_a_swarm_declared_dead() -> None:
    """Рой признан мёртвым — обрываем ffprobe сразу, а не досиживаем весь timeout."""
    began = time.monotonic()
    with pytest.raises(InfraError, match="рой молчит"):
        stream_mod._run_ffprobe(["sleep", "40"], timeout=40.0, alive=lambda: False)
    assert time.monotonic() - began < 3.0


def test_run_ffprobe_keeps_the_full_budget_while_the_stream_is_alive() -> None:
    """Пока поток жив, бюджет тратится полностью и таймаут остаётся прежним."""
    began = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        stream_mod._run_ffprobe(["sleep", "40"], timeout=0.5, alive=lambda: True)
    assert 0.4 <= time.monotonic() - began < 4.0


class _Body:
    def __init__(self, chunk: bytes) -> None:
        self._chunk = chunk

    def __enter__(self) -> _Body:
        return self

    def __exit__(self, *_: object) -> Literal[False]:
        return False

    def read(self, _size: int) -> bytes:
        return self._chunk


def test_swarm_pulse_calls_a_byteless_stream_dead_only_after_the_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ни байта за отсрочку — рой мёртв; но пока отсрочка идёт, ждём: рой ещё может ожить."""
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Body(b""))
    alive = swarm_pulse("http://ts/x/0", grace=0.2)
    assert alive()  # отсрочка не вышла - терпим
    time.sleep(0.3)
    assert not alive()  # байт нет и отсрочка вышла - рой молчит


def test_swarm_pulse_stays_alive_once_a_byte_arrives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пришёл байт — раздача жива и читается: обрывать её нельзя даже после отсрочки."""
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Body(b"\x00" * 4096))
    alive = swarm_pulse("http://ts/x/0", grace=0.05)
    time.sleep(0.2)  # отсрочка давно вышла
    assert alive()  # но байт был - раздача честно читается


def test_a_silent_stream_is_dropped_before_the_full_probe_budget(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Верх молчит потоком (метаданные есть, содержимого нет) — отказ приходит за отсрочку,
    а не за все сорок секунд PROBE_BUDGET, и показ уходит к живому запасному.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    monkeypatch.setattr(Release, "magnet", property(lambda self: f"magnet-{self.raw_name}"))
    monkeypatch.setattr(cli, "SWARM_GRACE", 0.3)

    def read(url: str, timeout: float = 90.0, alive: Any = None) -> Media:
        if "hash-magnet-r0/" in url:  # верх: рой молчит потоком
            end = time.monotonic() + timeout
            while alive is None or alive():
                if time.monotonic() >= end:
                    raise InfraError("ffprobe не дождался потока")
                time.sleep(0.02)
            raise InfraError("рой молчит - за отсрочку не пришло ни байта потока")
        return Media(3600.0, (), "h264")

    monkeypatch.setattr(cli, "probe", read)

    began = time.monotonic()
    prep = _resolve(cli._Bench(cast(Any, _FakeTorrServer())), ranked)
    elapsed = time.monotonic() - began

    printed = capsys.readouterr().out
    assert prep.number == 2, "молчащий поток не останавливает показ"
    assert "релиз 1 не годится (рой молчит" in printed and "беру 2" in printed
    assert elapsed < cli.PROBE_BUDGET, "не сожгли весь бюджет на молчащем релизе"


# --- Шаг опроса метаданных (TC-126) ---------------------------------------------------
#
# Ожидание метаданных устранить нельзя: TorrServer не отдаст ни байта, пока рой их не
# привезёт. Устранима только наша добавка к нему - остаток шага опроса. С прежней
# секундой она была видна в замерах глазами: все времена ожидания выходили почти целыми
# (2.01, 3.01, 5.01, 8.02, 11.02, 12.02 с), то есть в среднем полсекунды на каждом
# старте мы досыпали уже поверх готовых метаданных.


class _Late(stream_mod.TorrServer):
    """Клиент TorrServer, у которого метаданные приезжают в назначенный момент времени.

    Именно по времени, а не «на N-м опросе»: шаг опроса как раз и меняет число опросов,
    и счётчик мерил бы не то. Единственный поход по сети подменён, остальной
    :meth:`~torrcast.stream.TorrServer.wait_files` живой.
    """

    def __init__(self, ready_after: float) -> None:
        super().__init__("http://torrserver.invalid")
        self.ready = time.monotonic() + ready_after
        self.polls = 0

    def files(self, torrent_hash: str) -> list[stream_mod.TorrFile]:
        self.polls += 1
        if time.monotonic() < self.ready:
            return []
        return [stream_mod.TorrFile(0, "film.mkv", 8 << 30)]


def test_metadata_are_taken_up_within_a_step_not_within_a_second() -> None:
    """Пришедшие метаданные ждут нас не дольше одного шага опроса.

    Это и есть цена вопроса: показ стартует настолько позже роя, насколько крупен шаг.
    """
    client = _Late(0.3)
    began = time.monotonic()
    assert client.wait_files("hash", timeout=5.0), "метаданные всё-таки приехали"
    late = time.monotonic() - began - 0.3
    assert late <= stream_mod.META_STEP_MAX + 0.05, f"метаданные пролежали лишние {late:.2f} с"


def test_the_poll_never_turns_into_a_flood() -> None:
    """Мелкий шаг - не повод долбить TorrServer: частота опроса имеет потолок."""
    client = _Late(0.5)
    client.wait_files("hash", timeout=5.0)
    ceiling = 0.5 / stream_mod.META_STEP_MAX + 4  # +4 - разгон лестницы с мелкого шага
    assert client.polls <= ceiling, f"{client.polls} опросов за полсекунды - это долбёжка"


def test_the_metadata_deadline_is_a_deadline() -> None:
    """Срок ожидания - это срок, а не «до конца ближайшего шага после него».

    Последний сон подрезается по сроку: иначе на мёртвом рое короткий бюджет всё равно
    округлялся бы вверх до целого шага, и отказ приходил бы позже, чем обещан.
    """
    client = _Late(99.0)  # рой молчит и будет молчать
    began = time.monotonic()
    with pytest.raises(InfraError, match="не отдала метаданные"):
        client.wait_files("hash", timeout=0.35)
    spent = time.monotonic() - began
    assert 0.35 <= spent < 0.45, f"обещали ждать 0.35 с, ждали {spent:.2f} с"


# --- Потолок кэшей карт и паспортов (TC-127) ------------------------------------------
#
# Карта опорных кадров снимается у роя (первое чтение хвоста стоит 13-24 с), и полка
# существует ровно затем, чтобы не платить рою второй раз. Но потолка у неё не было
# вовсе: на живой полке 299 карт весят 8.7 МБ (медиана 22 КБ, самая большая - 874 КБ), и
# на инструменте, который работает годами, это тихий рост диска без единой строки наружу.


def _fake_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """Снятие карты без роя и без файла: тут проверяется полка, а не разбор Cues."""
    import torrcast.keymap as keymap_mod

    def keyframes(_: str) -> Any:
        return keymap_mod.KeyMap(60.0, (keymap_mod.Point(0.0, 0, 0),), 0, 0, "mkv")

    monkeypatch.setattr(keymap_mod, "keyframes", keyframes)


def _url(number: int) -> str:
    return f"http://torrserver.invalid/stream?link={number:040x}&index=0"


def test_the_key_shelf_is_trimmed_and_what_was_asked_today_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Полка карт не растёт без предела, и вытесняется давно не спрашиваемое.

    Вытеснение идёт по времени **обращения**, а не создания: карта фильма, который
    смотрят каждый вечер, снимается один раз, и возраст сделал бы её первой кандидаткой
    на вылет - то есть кэш выбрасывал бы ровно то, ради чего он заведён.
    """
    from torrcast.stream import _keys_cache, film_keys

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(stream_mod, "KEYS_KEPT", 8)
    _fake_map(monkeypatch)

    for number in range(8):  # полка ровно под потолок, и вся она «старая»
        film_keys(_url(number))
        os.utime(_keys_cache(_url(number)), (number, number))
    assert film_keys(_url(0)).duration == 60.0, "старейшую карту взяли с полки"

    for number in range(100, 104):  # четыре новых фильма выдавливают полку за потолок
        film_keys(_url(number))
    shelf = _keys_cache(_url(0)).parent
    left = {path.stem for path in shelf.glob("*.json")}
    assert len(left) <= 8, f"полка переросла потолок: {len(left)} карт"
    assert _keys_cache(_url(0)).stem in left, "карту, которую смотрят, вытеснять нельзя"
    assert _keys_cache(_url(1)).stem not in left, "давно не спрошенное ушло"
    assert _keys_cache(_url(103)).stem in left, "только что снятая карта осталась"


def test_the_probe_shelf_is_trimmed_by_the_same_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """У паспортов полка своя, но правило то же: потолок и время обращения.

    Паспортов заводится больше, чем карт: их снимают и на релизы, которые показом так и
    не стали. Потому и потолок отдельный.
    """
    from torrcast.stream import _keep_media, _media_cache, _read_media

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(stream_mod, "PROBE_KEPT", 8)
    passport = Media(3600.0, (stream_mod.AudioTrack(0, "rus", "", "aac", 2),), "h264")

    for number in range(8):
        _keep_media(_media_cache(_url(number)), passport)
        os.utime(_media_cache(_url(number)), (number, number))
    assert _read_media(_media_cache(_url(0))) is not None, "старейший паспорт спросили"

    for number in range(100, 104):
        _keep_media(_media_cache(_url(number)), passport)
    shelf = _media_cache(_url(0)).parent
    left = {path.stem for path in shelf.glob("*.json")}
    assert len(left) <= 8, f"полка паспортов переросла потолок: {len(left)}"
    assert _media_cache(_url(0)).stem in left, "спрошенный сегодня паспорт остался"
    assert _media_cache(_url(1)).stem not in left, "давно не спрошенный ушёл"


def test_junk_on_the_shelf_is_ignored_and_never_crashes_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Битый, пустой или чужой файл на полке стоит одного снятия карты, а не старта.

    Полка - ускорение, а не источник правды. Заодно проверяется, что подрезка не трогает
    чужого: черновики и замки соседних писателей не её дело.
    """
    from torrcast.stream import _keys_cache, film_keys

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(stream_mod, "KEYS_KEPT", 4)
    _fake_map(monkeypatch)

    cache = _keys_cache(_url(0))
    cache.parent.mkdir(parents=True, exist_ok=True)
    alien = cache.parent / "чужое.lock"
    alien.write_text("не наше дело", "utf-8")
    for junk in ('{"duration": 60.0, "keys": [0.0, 1', "", '{"keys": []}', "[1, 2, 3]"):
        cache.write_text(junk, "utf-8")
        assert film_keys(_url(0)).duration == 60.0, f"мусор {junk!r} уронил старт"
        assert cache.read_text("utf-8") != junk, "мусор перезаписан снятой картой"

    for number in range(20):  # подрезка обязана пережить мусор рядом
        cache.with_name(f"{number:016x}.json").write_text("не json", "utf-8")
        film_keys(_url(number + 1))
    assert alien.exists(), "подрезка тронула чужой файл"


def test_trimming_does_not_hold_up_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Подрезка идёт в общей нитке с показом, поэтому её цена названа числом.

    Полная полка, худший случай - тот показ, на котором подрезка и случается: он платит
    полный обход со ``stat``. Всё остальное время это один ``scandir``.
    """
    from torrcast.stream import _keys_cache, _trim, film_keys

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    _fake_map(monkeypatch)
    film_keys(_url(0))
    shelf = _keys_cache(_url(0)).parent
    for number in range(stream_mod.KEYS_KEPT + 1):
        (shelf / f"{number:016x}.json").write_text("{}", "utf-8")

    began = time.monotonic()
    _trim(shelf, stream_mod.KEYS_KEPT)  # перебор потолка: полный обход и удаление
    worst = time.monotonic() - began
    began = time.monotonic()
    _trim(shelf, stream_mod.KEYS_KEPT)  # полка под потолком: один scandir
    usual = time.monotonic() - began
    assert worst < 0.1, f"подрезка полной полки стоила {worst * 1000:.1f} мс"
    assert usual < 0.02, f"обычная проверка полки стоила {usual * 1000:.1f} мс"
