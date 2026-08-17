"""Проверяет снятие карты опорных кадров: полка, замок под работающим читателем, черновик."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack.film_keys import _fetching, _keys_draft, film_keys
from torrcast.domain.frames.keymap import KeyMap, Point

#: Модуль, а не одноимённая единица из пакета: подмена ставится туда, откуда её
#: читает сам код.
module = module_of("torrcast.adapters.stream_pack.film_keys")

URL = "http://127.0.0.1:8090/stream?link=0123456789abcdef&index=1"


def _map(seconds: float = 60.0) -> KeyMap:
    return KeyMap(seconds, (Point(0.0, 0, 0), Point(2.0, 4096, 0)), 0, 0, "mkv")


@pytest.fixture(autouse=True)
def _own_shelf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


def test_the_map_is_taken_from_the_shelf_instead_of_the_swarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Второй показ того же файла за хвост не платит: карта уже лежит на полке.

    Первое чтение хвоста у холодного роя стоит 13.8-24.4 с, и продолжение с середины -
    обычное дело.
    """
    asked: list[str] = []

    def once(url: str) -> KeyMap:
        asked.append(url)
        return _map()

    monkeypatch.setattr(module, "keyframes", once)
    first = film_keys(URL)
    second = film_keys(URL)
    assert asked == [URL], f"карту сняли {len(asked)} раза вместо одного"
    assert (first.at, first.offset, first.kind) == ([0.0, 2.0], [0, 4096], "mkv")
    assert second == first
    assert _keys_cache(URL).exists()


def test_only_the_video_track_gets_into_the_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сетка стоит на опорных кадрах ВИДЕО: чужая дорожка в карте разъехалась бы с ней."""
    # Дорожка 0 - звук: точек больше, а пробелы в ней втрое шире, чем у видео.
    sound = tuple(Point(place, int(place * 10), 0) for place in (0.0, 1.0, 2.0, 32.0, 33.0, 60.0))
    video = tuple(Point(place, int(place * 100), 3) for place in (0.0, 10.0, 20.0, 30.0, 40.0))
    points = tuple(sorted(sound + video, key=lambda point: point.at))
    monkeypatch.setattr(module, "keyframes", lambda url: KeyMap(60.0, points, 0, 0, "mkv"))
    ready = film_keys(URL)
    assert ready.at == [0.0, 10.0, 20.0, 30.0, 40.0], "в карту попала не дорожка видео"
    assert ready.offset == [0, 1000, 2000, 3000, 4000]


@pytest.mark.machine
def test_a_reader_waits_for_the_neighbour_instead_of_reading_the_tail_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Карту уже снимает прогрев - ждём его, а не читаем индекс вторым потоком.

    Рой от второго читателя быстрее не станет, а старт показа удвоится.
    """
    monkeypatch.setattr(module, "KEYS_LOCK", 5.0)
    monkeypatch.setattr(module, "KEYS_WAIT", 5.0)
    cache = _keys_cache(URL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    lock = cache.with_suffix(".lock")
    lock.touch()

    def never(url: str) -> KeyMap:
        raise AssertionError("сосед полез в рой, хотя карту уже снимают")

    monkeypatch.setattr(module, "keyframes", never)

    def neighbour() -> None:
        time.sleep(0.2)
        cache.write_text(
            json.dumps({"duration": 42.0, "keys": [0.0], "bytes": [0], "kind": "mkv"}), "utf-8"
        )

    threading.Thread(target=neighbour, daemon=True).start()
    assert film_keys(URL).duration == 42.0


@pytest.mark.machine
def test_the_lock_stays_alive_while_its_holder_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """Замок живёт по mtime, и пока его держат, mtime обязан идти вперёд.

    Иначе сосед, заглянувший на середине долгого разбора, увидит протухший замок и
    полезет читать тот же хвост вторым потоком - ровно то, ради чего замок и заведён.
    """
    monkeypatch.setattr(module, "KEYS_LOCK", 0.3)  # 60 с в проде: столько не ждём
    lock = _keys_cache(URL).with_suffix(".lock")
    alive: list[bool] = []

    def slow(url: str) -> KeyMap:
        for _tick in range(6):  # 0.6 с работы против 0.3 с жизни замка
            time.sleep(0.1)
            alive.append(_fetching(lock))
        return _map()

    monkeypatch.setattr(module, "keyframes", slow)
    film_keys(URL)
    assert all(alive), f"замок протух под работающим читателем: {alive}"
    assert not lock.exists(), "замок обязан сниматься после записи кэша"


@pytest.mark.machine
def test_two_writers_of_one_map_do_not_share_a_draft() -> None:
    """Черновик кэша - файл на писателя, а не на URL: иначе наружу уехала бы склейка."""
    cache = _keys_cache(URL)
    mine = _keys_draft(cache)
    assert mine != cache and mine.name.endswith(".tmp")

    others: list[Path] = []
    thread = threading.Thread(target=lambda: others.append(_keys_draft(cache)))
    thread.start()
    thread.join()
    assert others[0] != mine, "два писателя пишут в одно имя"


def test_a_swarm_that_says_nothing_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Беда снятия карты уезжает наружу: сетку по ней не построить, и молчать нельзя."""

    def dead(url: str) -> Any:
        raise OSError("рой молчит")

    monkeypatch.setattr(module, "keyframes", dead)
    with pytest.raises(OSError, match="рой молчит"):
        film_keys(URL)
    assert not _keys_cache(URL).with_suffix(".lock").exists(), "замок остался за мёртвым читателем"
