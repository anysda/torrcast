"""Проверяет снятие карты опорных кадров: полка, замок под работающим читателем, черновик."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
from torrcast.adapters.stream_pack.film_keys import _fetching, film_keys
from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.adapters.stream_pack.weigh_keys import weigh_keys
from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.point import Point
from torrcast.domain.ghost_keys_error import GhostKeysError
from torrcast.domain.infra_error import InfraError
from torrcast.domain.swarm_silent_error import SwarmSilentError
from torrcast.domain.warm_open import KEYS_RULES

URL = "http://127.0.0.1:8090/stream?link=0123456789abcdef&index=1"


def _map(seconds: float = 60.0) -> KeyMap:
    return KeyMap(seconds, (Point(0.0, 0, 0), Point(2.0, 4096, 0)), 0, 0, "mkv")


@pytest.fixture(autouse=True)
def _own_shelf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


def test_the_map_is_taken_from_the_shelf_instead_of_the_swarm() -> None:
    """Второй показ того же файла за хвост не платит: карта уже лежит на полке.

    Первое чтение хвоста у холодного роя стоит 13.8-24.4 с, и продолжение с середины -
    обычное дело.
    """
    asked: list[str] = []

    def once(url: str) -> KeyMap:
        asked.append(url)
        return _map()

    first = film_keys(URL, keys_of=once)
    second = film_keys(URL, keys_of=once)
    assert asked == [URL], f"карту сняли {len(asked)} раза вместо одного"
    assert (first.at, first.offset, first.kind) == ([0.0, 2.0], [0, 4096], "mkv")
    assert second == first
    assert _keys_cache(URL).exists()


def test_only_the_video_track_gets_into_the_map() -> None:
    """Сетка стоит на опорных кадрах ВИДЕО: чужая дорожка в карте разъехалась бы с ней.

    Файл дорожку не назвал (``KeyMap.video`` пуст) - выбирает эвристика-запасной путь.
    """
    # Дорожка 0 - звук: точек больше, а пробелы в ней втрое шире, чем у видео.
    sound = tuple(Point(place, int(place * 10), 0) for place in (0.0, 1.0, 2.0, 32.0, 33.0, 60.0))
    video = tuple(Point(place, int(place * 100), 3) for place in (0.0, 10.0, 20.0, 30.0, 40.0))
    points = tuple(sorted(sound + video, key=lambda point: point.at))
    ready = film_keys(URL, keys_of=lambda url: KeyMap(60.0, points, 0, 0, "mkv"))
    assert ready.at == [0.0, 10.0, 20.0, 30.0, 40.0], "в карту попала не дорожка видео"
    assert ready.offset == [0, 1000, 2000, 3000, 4000]


def test_the_track_named_by_the_file_wins_over_the_guess() -> None:
    """Файл назвал дорожку видео сам (``Tracks``) - эвристика не спрашивается.

    Эвристика тут выбрала бы звук (дорожка 0): у неё точки через секунду ровно, а у видео
    - раз в десять. Замер TC-639 на живом файле: ровный шаг бывает и у мусорного индекса,
    поэтому слово файла сильнее любой закономерности.
    """
    sound = tuple(Point(float(place), place * 10, 0) for place in range(61))
    video = tuple(Point(float(place), place * 100, 3) for place in range(0, 61, 10))
    points = tuple(sorted(sound + video, key=lambda point: point.at))
    ready = film_keys(URL, keys_of=lambda url: KeyMap(60.0, points, 0, 0, "mkv", 3))
    assert ready.at == [float(place) for place in range(0, 61, 10)], (
        "названная файлом дорожка проиграла эвристике"
    )


def test_the_seek_time_is_filtered_with_its_track() -> None:
    """Исковое время (``via``) сокращается до дорожки видео вместе с точками карты.

    Разойдись эти ряды длиной - и бисект в ``mapped_start`` пошёл бы по чужим меткам,
    поэтому ряды склеены ``zip(strict=True)``: сдвинутый ряд роняет разбор, а не режет.
    """
    sound = tuple(Point(place, int(place * 10), 0) for place in (0.0, 30.0))
    video = tuple(Point(place, int(place * 100), 3) for place in (10.0, 20.0))
    points = tuple(sorted(sound + video, key=lambda point: point.at))
    via = tuple(point.at - 0.08 for point in points)  # исковое время чуть раньше метки
    ready = film_keys(URL, keys_of=lambda url: KeyMap(60.0, points, 0, 0, "mp4", 3, via))
    assert list(ready.via) == [9.92, 19.92], "исковое время потеряло дорожку видео"


@pytest.mark.machine
def test_a_reader_waits_for_the_neighbour_instead_of_reading_the_tail_twice() -> None:
    """Карту уже снимает прогрев - ждём его, а не читаем индекс вторым потоком.

    Рой от второго читателя быстрее не станет, а старт показа удвоится.
    """
    cache = _keys_cache(URL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    lock = cache.with_suffix(".lock")
    lock.touch()

    def never(url: str) -> KeyMap:
        raise AssertionError("сосед полез в рой, хотя карту уже снимают")

    def neighbour() -> None:
        time.sleep(0.2)
        cache.write_text(
            json.dumps(
                {"duration": 42.0, "keys": [0.0], "bytes": [0], "kind": "mkv", "rules": KEYS_RULES}
            ),
            "utf-8",
        )

    threading.Thread(target=neighbour, daemon=True).start()
    assert film_keys(URL, keys_of=never, lock_ttl=5.0, wait=5.0).duration == 42.0


@pytest.mark.machine
def test_the_lock_stays_alive_while_its_holder_works() -> None:
    """Замок живёт по mtime, и пока его держат, mtime обязан идти вперёд.

    Иначе сосед, заглянувший на середине долгого разбора, увидит протухший замок и
    полезет читать тот же хвост вторым потоком - ровно то, ради чего замок и заведён.
    """
    ttl = 0.3  # 60 с в проде: столько не ждём
    lock = _keys_cache(URL).with_suffix(".lock")
    alive: list[bool] = []

    def slow(url: str) -> KeyMap:
        for _tick in range(6):  # 0.6 с работы против 0.3 с жизни замка
            time.sleep(0.1)
            alive.append(_fetching(lock, ttl))
        return _map()

    film_keys(URL, keys_of=slow, lock_ttl=ttl)
    assert all(alive), f"замок протух под работающим читателем: {alive}"
    assert not lock.exists(), "замок обязан сниматься после записи кэша"


def test_a_swarm_that_says_nothing_is_not_swallowed() -> None:
    """Беда снятия карты уезжает наружу: сетку по ней не построить, и молчать нельзя."""

    def dead(url: str) -> Any:
        raise OSError("рой молчит")

    with pytest.raises(OSError, match="рой молчит"):
        film_keys(URL, keys_of=dead)
    assert not _keys_cache(URL).with_suffix(".lock").exists(), "замок остался за мёртвым читателем"


def test_a_verdict_about_the_file_is_paid_once_and_not_on_every_start() -> None:
    """«Индекс Cues врёт» - ответ про сам файл: он ложится на полку рядом с картами.

    Иначе каждый старт такого фильма платит заново - голову, весь индекс (у измеренного
    файла 151 КБ) и пробы честности, - а сессия с прогревом и показом платит это дважды.
    """
    asked: list[str] = []

    def lying(url: str) -> Any:
        asked.append(url)
        raise InfraError("индекс Cues врёт: точка 1234.567 ссылается не на опорный кадр")

    for _start in range(3):
        with pytest.raises(InfraError, match="индекс Cues врёт"):
            film_keys(URL, keys_of=lying)
    assert asked == [URL], f"за вердиктом сходили в рой {len(asked)} раза вместо одного"
    assert not _keys_cache(URL).with_suffix(".lock").exists(), "замок остался за отказом"


def test_an_unknown_container_is_remembered_the_same_way() -> None:
    """Отказ запоминается по одному правилу, а не по списку известных слов."""
    asked: list[str] = []

    def strange(url: str) -> Any:
        asked.append(url)
        raise InfraError("это не mkv и не mp4: карту опорных кадров взять неоткуда")

    for _start in range(2):
        with pytest.raises(InfraError, match="не mkv и не mp4"):
            film_keys(URL, keys_of=strange)
    assert asked == [URL], "незнакомый контейнер разбирался повторно"


def test_a_silent_swarm_is_not_remembered_as_a_bad_file() -> None:
    """Раздача бывает холодной минуту и живой через минуту - молчание роя не про файл.

    Запомни мы его - и фильм остался бы на ровной сетке из-за чужой беды.
    """
    asked: list[str] = []

    def cold(url: str) -> Any:
        asked.append(url)
        raise SwarmSilentError("не читается голова файла: соединение отвергнуто")

    for _start in range(3):
        with pytest.raises(SwarmSilentError):
            film_keys(URL, keys_of=cold)
    assert len(asked) == 3, "молчание роя запомнили как приговор файлу"
    assert not _keys_cache(URL).exists(), "на полке лежит вердикт, которого не выносили"


def test_a_forgotten_verdict_gives_the_file_a_new_chance() -> None:
    """Срок вышел - файл судится заново, и починенный индекс получает свою сетку."""
    asked: list[str] = []

    def once_lying(url: str) -> KeyMap:
        asked.append(url)
        if len(asked) == 1:
            raise InfraError("индекс Cues врёт")
        return _map()

    with pytest.raises(InfraError):
        film_keys(URL, keys_of=once_lying, refused_ttl=0.0)
    assert film_keys(URL, keys_of=once_lying, refused_ttl=0.0).duration == 60.0
    assert len(asked) == 2, "забытый вердикт не пустил файл на пересуд"
    assert read_keys(_keys_cache(URL)) is not None, "карта не легла на место отказа"


def test_refusals_do_not_grow_the_shelf_past_its_ceiling() -> None:
    """Полка общая с картами, и потолок у неё общий: отказ - такой же ответ про файл.

    Ложись отказы мимо подрезки - и полка росла бы теми самыми фильмами, у которых
    карты не будет никогда.
    """

    def lying(url: str) -> Any:
        raise InfraError("индекс Cues врёт")

    kept = 4
    for number in range(12):
        with pytest.raises(InfraError):
            film_keys(f"{URL}&file={number}", keys_of=lying, kept=kept)
    shelf = list(_keys_cache(URL).parent.glob("*.json"))
    assert len(shelf) <= kept, f"полка выросла до {len(shelf)} карточек при потолке {kept}"


@pytest.mark.machine
def test_a_reader_takes_the_neighbours_refusal_instead_of_reading_the_tail_itself() -> None:
    """Прогрев кончил отказом - показу ждать больше нечего и читать хвост незачем.

    Ровно тут сессия с прогревом и показом платила цену подготовки дважды: сосед
    отказывался молча, замок исчезал, и показ шёл в рой за тем же ответом.
    """
    cache = _keys_cache(URL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    lock = cache.with_suffix(".lock")
    lock.touch()

    def never(url: str) -> KeyMap:
        raise AssertionError("показ полез в рой за ответом, который уже дал прогрев")

    def neighbour() -> None:
        time.sleep(0.2)
        cache.write_text(json.dumps({"refused": "индекс Cues врёт", "when": time.time()}), "utf-8")

    threading.Thread(target=neighbour, daemon=True).start()
    with pytest.raises(InfraError, match="индекс Cues врёт"):
        film_keys(URL, keys_of=never, lock_ttl=5.0, wait=5.0)


def test_a_ghost_index_leaves_its_honest_byte_row_on_the_shelf() -> None:
    """🔴 TC-840. Индекс признан призрачным - вердикт ложится ВМЕСТЕ с его смещениями.

    Врущий индекс отвергает у карты одно утверждение - «здесь стоит опорный кадр», - а
    пара «время - смещение» у него честная: это позиции кластеров контейнера. По ней
    считается ВЕС куска, и без неё ровная сетка остаётся без профиля тяжести
    (`профиль 0.0`): кодировщик не берёт ни куска впрок, и КАЖДЫЙ уходит ужатием на месте.
    Живой сеанс 27-08 на «Матрице» 1999: 59 кусков из 59 ужатием и три вылета приёмника
    за 58 минут против нуля накануне.

    Полка при этом остаётся полкой ОТКАЗА: картой такая запись не становится
    (:func:`read_keys` молчит на всём, где стоит вердикт), а весом - становится
    (:func:`weigh_keys`). Разъедься эти два читателя - вердикт отменил бы сам себя.
    """
    drawn = KeyMap(60.0, tuple(Point(float(k * 2), k * 4096, 1) for k in range(31)), 0, 0, "mkv", 1)

    def ghost(url: str) -> KeyMap:
        raise GhostKeysError("индекс Cues врёт: точка 4131.693", drawn)

    with pytest.raises(InfraError, match="индекс Cues врёт"):
        film_keys(URL, keys_of=ghost)

    weighed = weigh_keys(_keys_cache(URL))
    assert weighed is not None, "указатель веса потерян вместе с приговором кадрам"
    assert weighed.at == [float(k * 2) for k in range(31)]
    assert weighed.offset == [k * 4096 for k in range(31)]
    assert read_keys(_keys_cache(URL)) is None, "отвергнутая карта вернулась сеткой показа"


def test_an_index_that_never_parsed_leaves_nothing_to_weigh_by() -> None:
    """Отрицательная проба к предыдущей: индекса не нашлось - взвешивать нечем и незачем.

    Разница здесь не в громкости отказа, а в том, что у него на руках: призрачный индекс
    разобран до последней точки, а «индекса нет» - это отсутствие самих точек. Выдай полка
    вес и на такой записи, она выдумала бы его из ничего.
    """

    def missing(url: str) -> KeyMap:
        raise InfraError("в файле нет индекса Cues - карту опорных кадров взять неоткуда")

    with pytest.raises(InfraError, match="нет индекса Cues"):
        film_keys(URL, keys_of=missing)

    assert weigh_keys(_keys_cache(URL)) is None, "вес взялся у файла, чей индекс не разобран"
