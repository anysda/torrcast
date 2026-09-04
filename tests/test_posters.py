"""Зеркало :mod:`hass.posters`: картинка играющего - постер, а нет его - кадр показа."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hass.both_posters import BothPosters
from hass.hit_posters import HitPosters
from hass.poster_shelf import PosterShelf
from hass.posters import ROUTE, Posters
from tests.test_hit_posters import FakeSource
from torrcast.adapters.ffmpeg.frame_shot import frame_shot
from torrcast.adapters.wiki.imdb_poster import ImdbPoster
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.domain.facts.ask import Ask
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.runtime.facts_wiring import FACTS

POSTER = b"\xff\xd8\xff\xe0poster"
OTHER = b"\xff\xd8\xff\xe0another poster"
FRAME = b"\xff\xd8\xff\xe0frame"
STREAM = "http://10.0.1.5:8010/stream/index.m3u8"

#: Сколько ждём фоновую работу в пробе, секунды. Работа тут вся на подделках и стоит
#: миллисекунды; потолок нужен против зависшей пробы, а не против медленной сети.
_SETTLE = 5.0


def _film(
    title: str = "Тачки", year: int = 2006, label: str = "", original: str = "", query: str = ""
) -> PlaybackSnapshot:
    return PlaybackSnapshot(
        key="k", title=title, year=year, label=label, original=original, query=query
    )


@dataclass
class FakePoster:
    """Двойник похода в Википедию: помнит, о чём спрашивали, и отвечает, чем велено."""

    body: bytes | None = POSTER
    error: Exception | None = None
    gate: threading.Event | None = None
    asked: list[tuple[str, int | None, str]] = field(default_factory=list)

    def __call__(self, ask: Ask, timeout: float) -> bytes | None:
        self.asked.append((ask.title, ask.year, ask.kind))
        if self.gate is not None:
            self.gate.wait(_SETTLE)
        if self.error is not None:
            raise self.error
        return self.body


@dataclass
class FakeFrame:
    """Двойник ffmpeg: кадр из показа, без подпроцесса."""

    body: bytes | None = FRAME
    asked: list[str] = field(default_factory=list)

    def __call__(self, source: str) -> bytes | None:
        self.asked.append(source)
        return self.body


@dataclass
class LateFrame:
    """Двойник ffmpeg на СТАРТЕ показа: сетка раздачи открывается не с первой секунды.

    Живой замер на стенде: манифест читается ffmpeg только с 4.3 с показа, а первый
    опрос карточки приходит на 2 с. Промах тут - это «ещё рано», а не «кадра нет».
    """

    misses: int = 2
    body: bytes = FRAME
    asked: list[str] = field(default_factory=list)

    def __call__(self, source: str) -> bytes | None:
        self.asked.append(source)
        return None if len(self.asked) <= self.misses else self.body


def _posters(
    poster: FakePoster,
    frame: FakeFrame | LateFrame,
    home: Path,
    now: float = 0.0,
    pause: Callable[[float], None] = lambda _: None,
) -> tuple[Posters, list[float]]:
    """Картинки на подделках; часы отдаются списком, чтобы проба двигала их сама.

    Пауза между попытками кадра тут пустая: ждать её по-настоящему значило бы держать
    пробу секундами ради того, что подделка решает мгновенно.
    """
    clock = [now]
    made = Posters(
        poster=poster,
        frame=frame,
        shelf=PosterShelf(home=lambda: home / "posters"),
        now=lambda: clock[0],
        pause=pause,
    )
    return made, clock


def _settled(
    made: Posters, shown: PlaybackSnapshot, stream: str = STREAM, want: bytes | None = None
) -> tuple[str, str]:
    """Опрашивать снимок, пока фоновая работа не ответит; не ответила - пусто.

    Так его и опрашивает Home Assistant: раз в несколько секунд, тем же вызовом. Ждать
    внутри :meth:`Posters.picture` нельзя - на время похода в Википедию замерла бы вся
    карточка, - поэтому проба ждёт снаружи, как ждёт живой опрос.

    🔴 Ждать сказано ИМЕННО ТУ картинку, о которой проба. Картинок за показ приезжает
    две - кадр, а следом сменяющий его постер, - и «первая непустая» отдавала бы то одну,
    то другую по жребию планировщика: проба про постер зеленела бы на кадре.
    """
    end = time.monotonic() + _SETTLE
    while time.monotonic() < end:
        answer = made.picture(shown, lambda: stream)
        got = made.read(answer[1]) if answer[1] else None
        if answer != ("", "") and (want is None or (got is not None and got[0] == want)):
            return answer
        time.sleep(0.01)
    return "", ""


@pytest.mark.machine
def test_the_first_poll_answers_empty_and_the_picture_arrives_next(tmp_path: Path) -> None:
    """Работа идёт фоном: снимок отвечает тем, что готово, а не ждёт Википедию.

    Замри он на походе в сеть - вместе с ним замерли бы полоса времени и пульт карточки.
    """
    poster, frame = FakePoster(), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)
    shown = _film()

    assert made.picture(shown, lambda: STREAM) == ("", ""), "первый опрос не ждёт сети"

    address, digest = _settled(made, shown, want=POSTER)
    assert address == ROUTE + digest
    assert made.read(digest) == (POSTER, "image/jpeg")


@pytest.mark.machine
def test_the_address_names_the_serve_and_no_outside_host(tmp_path: Path) -> None:
    """🔴 Наружу за картинкой Home Assistant не ходит ни при каких условиях.

    Отдай карточке адрес Wikimedia - и тянул бы её клиент, через ту самую сеть, где
    режут по SNI. Байты скачивает серв, а карточке отдаёт своим маршрутом.
    """
    made, _ = _posters(FakePoster(), FakeFrame(), tmp_path)

    address, _ = _settled(made, _film())

    assert address.startswith(ROUTE)
    assert "http" not in address and "wikimedia" not in address


@pytest.mark.machine
def test_the_fingerprint_follows_the_bytes_and_not_the_name(tmp_path: Path) -> None:
    """🔴 Без смены отпечатка Home Assistant прилепит первую картинку навсегда.

    ``media_image_hash`` - ровно тот ключ, которым он решает, тянуть ли картинку заново.
    Отпечаток берётся от БАЙТОВ: у нового показа они другие, и картинка сменится.
    """
    poster, frame = FakePoster(), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)

    _, first = _settled(made, _film(), want=POSTER)
    poster.body = OTHER
    _, second = _settled(made, _film("Брат", 1997), want=OTHER)

    assert first == hashlib.sha256(POSTER).hexdigest()[:16]
    assert second != first


@pytest.mark.machine
def test_a_picture_without_a_poster_shows_a_frame_of_the_show(tmp_path: Path) -> None:
    """Запасной путь: карточка не остаётся молча пустой, когда постера не нашлось."""
    poster, frame = FakePoster(body=None), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)

    _, digest = _settled(made, _film("Внутри Лапенко", 2019, "s1e1"), want=FRAME)

    assert frame.asked == [STREAM], "кадр берётся с собственной раздачи, не из сети"
    assert made.read(digest) == (FRAME, "image/jpeg")


@pytest.mark.machine
def test_a_silent_wikipedia_does_not_leave_the_card_empty(tmp_path: Path) -> None:
    """429 и оборванная сеть для карточки значат то же, что «статьи нет»: нужен кадр."""
    poster, frame = FakePoster(error=OSError("HTTP 429")), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)

    _, digest = _settled(made, _film(), want=FRAME)

    assert made.read(digest) == (FRAME, "image/jpeg")


@pytest.mark.machine
def test_the_frame_reaches_the_card_while_the_poster_is_still_on_its_way(
    tmp_path: Path,
) -> None:
    """🔴 Кадр не ждёт провала постера: карточка заполнена с первых секунд показа.

    Постер едет из сети до полуминуты - два имени, два источника, восемь секунд сроку на
    запрос, - и всё это время карточка стояла пустой. Здесь Википедия держится закрытой
    задвижкой ровно так же, как держит её живая сеть, и картинка обязана приехать ДО
    того, как задвижка откроется. Снимись кадр после постера - проба зависла бы на
    задвижке и вернула бы пустоту.
    """
    gate = threading.Event()
    poster, frame = FakePoster(gate=gate), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)
    shown = _film()

    try:
        address, digest = _settled(made, shown, want=FRAME)
    finally:
        gate.set()

    assert address == ROUTE + digest, "карточке есть что показать при молчащей Википедии"
    assert made.read(digest) == (FRAME, "image/jpeg"), "и это кадр показа"
    assert frame.asked == [STREAM], "кадр снят с собственной раздачи"


@pytest.mark.machine
def test_the_arriving_poster_takes_the_place_of_the_frame(tmp_path: Path) -> None:
    """Кадр держит карточку до постера и уступает ему, а не остаётся на весь показ.

    🔴 Отпечаток обязан СМЕНИТЬСЯ: им Home Assistant и решает, тянуть ли картинку заново.
    Останься он прежним - постер приехал бы на серв и не доехал бы до экрана.

    Старые байты при этом остаются достижимыми: отпечаток кадра уже уехал наружу
    предыдущим снимком, и запрос за ним не должен упереться в «нет такой картинки».
    """
    gate = threading.Event()
    poster, frame = FakePoster(gate=gate), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)
    shown = _film()

    _, shot = _settled(made, shown, want=FRAME)
    gate.set()
    _, drawn = _settled(made, shown, want=POSTER)

    assert drawn != shot, "отпечаток сменился вместе с картинкой"
    assert made.read(drawn) == (POSTER, "image/jpeg"), "карточка показывает постер"
    assert made.read(shot) == (FRAME, "image/jpeg"), "кадр ещё отдаётся по своему адресу"


@pytest.mark.machine
def test_a_late_frame_never_pushes_out_a_poster_that_arrived_first(tmp_path: Path) -> None:
    """🔴 Порядок картинок решает чтение, а не то, чей поток закончил раньше.

    ffmpeg бывает и медленнее сети: раздача холодная, сегмент ещё не выложен. Клади они
    картинку в одно место - опоздавший кадр затирал бы уже показанный постер, и карточка
    посреди фильма меняла бы обложку на кадр. Проба отпускает кадр ПОСЛЕ постера.
    """
    hold = threading.Event()
    poster = FakePoster()

    def slow(source: str) -> bytes | None:
        hold.wait(_SETTLE)
        return FRAME

    made = Posters(poster=poster, frame=slow, shelf=PosterShelf(home=lambda: tmp_path / "posters"))
    shown = _film()

    _, drawn = _settled(made, shown, want=POSTER)
    hold.set()
    time.sleep(0.05)

    assert made.picture(shown, lambda: STREAM) == (ROUTE + drawn, drawn), "постер на месте"
    assert made.read(drawn) == (POSTER, "image/jpeg")


@pytest.mark.machine
def test_a_shelved_poster_costs_no_frame_and_no_stream_address(tmp_path: Path) -> None:
    """Полка отвечает мгновенно - и гонять ffmpeg под неё незачем.

    Кадр снимается ради ожидания сети, а его тут нет вовсе: постер этой картины уже
    лежит на диске. Иначе каждая серия сериала заводила бы подпроцесс ради картинки,
    которой никто не увидит.
    """
    poster, frame = FakePoster(), FakeFrame()
    first, _ = _posters(poster, frame, tmp_path)
    _settled(first, _film(), want=POSTER)

    second, _ = _posters(poster, frame, tmp_path)
    asked: list[str] = []

    def stream() -> str:
        asked.append("да")
        return STREAM

    end = time.monotonic() + _SETTLE
    while second.picture(_film(), stream) == ("", "") and time.monotonic() < end:
        time.sleep(0.01)
    address, digest = second.picture(_film(), stream)

    assert address == ROUTE + digest and digest, "картинка приехала"
    assert second.read(digest) == (POSTER, "image/jpeg"), "и это постер с полки"
    assert asked == [], "за адресом раздачи никто не ходил"
    assert frame.asked == [STREAM], "кадр снят только в первый раз, когда полка была пуста"


@pytest.mark.machine
def test_a_show_without_a_stream_address_breaks_nothing(tmp_path: Path) -> None:
    """У оборванного показа на месте адреса стоит фраза для человека, а не ссылка."""
    poster, frame = FakePoster(body=None), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)
    shown = _film()

    made.picture(shown, lambda: "показ не идёт")
    end = time.monotonic() + _SETTLE
    while not poster.asked and time.monotonic() < end:
        time.sleep(0.01)
    time.sleep(0.05)

    assert frame.asked == [], "кадр по фразе для человека не снимают"
    assert made.picture(shown, lambda: "показ не идёт") == ("", "")


@pytest.mark.machine
def test_the_frame_opens_the_manifest_and_not_the_hls_base(tmp_path: Path) -> None:
    """Адрес сеанса - база HLS; ffmpeg нужен существующий мастер-манифест."""
    poster, frame = FakePoster(body=None), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)

    _, digest = _settled(made, _film("Картина без статьи"), "http://10.0.1.5:8010", want=FRAME)

    assert frame.asked == ["http://10.0.1.5:8010/index.m3u8"]
    assert made.read(digest) == (FRAME, "image/jpeg"), "карточка получила кадр"


@pytest.mark.machine
def test_a_misspelled_catalogue_title_reaches_a_poster_through_the_asked_words(
    tmp_path: Path,
) -> None:
    """Опечатка записи не хоронит постер: рядом с названием спрашивается запрос человека.

    Отдельного похода «за паспортом» тут больше нет - он подтверждал год у одной находки
    из девяти и стоил при этом запроса на каждую. Вместо него в очередь имён встаёт то,
    что человек и набрал, а год сверяет сам поход за статьёй.
    """
    asked: list[str] = []
    frame = FakeFrame()

    def poster(ask: Ask, timeout: float) -> bytes | None:
        asked.append(ask.title)
        return POSTER if ask.title == "еще по одной" else None

    made = Posters(
        poster=poster,
        frame=frame,
        shelf=PosterShelf(home=lambda: tmp_path / "posters"),
    )
    shown = _film("Еше по одной", 2020, original="Druk", query="еще-по-одной")

    _, digest = _settled(made, shown, want=POSTER)

    assert asked == ["Еше по одной", "еще по одной"], f"спрошено {asked}"
    assert made.read(digest) == (POSTER, "image/jpeg"), "карточка получила постер"


@pytest.mark.machine
def test_the_frame_is_never_put_on_the_shelf(tmp_path: Path) -> None:
    """🔴 Записанный на полку кадр означал бы, что постера у картины не будет никогда.

    Полка отвечает раньше сети: лёг на неё запасной кадр - и появившуюся английскую
    статью уже никто не спросит, ни в этом показе, ни в следующем году. Проба смотрит на
    саму полку, а потом заводит картинки заново - так, как их заводит перезапуск серва.
    """
    poster, frame = FakePoster(body=None), FakeFrame()
    shelf = PosterShelf(home=lambda: tmp_path / "posters")
    made, _ = _posters(poster, frame, tmp_path)
    shown = _film()

    _, digest = _settled(made, shown, want=FRAME)

    assert made.read(digest) == (FRAME, "image/jpeg"), "карточке уехал кадр"
    assert shelf.read("Тачки|2006|movie") is None, "кадр на полке"

    poster.body = POSTER
    after, _ = _posters(poster, frame, tmp_path)
    _, second = _settled(after, shown, want=POSTER)

    assert len(poster.asked) == 2, f"постер спрошен {len(poster.asked)} раз"
    assert after.read(second) == (POSTER, "image/jpeg")


@pytest.mark.machine
def test_a_shelved_poster_costs_no_trip_to_wikipedia(tmp_path: Path) -> None:
    """Второй показ той же картины отвечает с полки: сеть спрашивать не о чем."""
    poster, frame = FakePoster(), FakeFrame()
    first, _ = _posters(poster, frame, tmp_path)
    _settled(first, _film(), want=POSTER)

    second, _ = _posters(poster, frame, tmp_path)
    _, digest = _settled(second, _film(), want=POSTER)

    assert len(poster.asked) == 1, f"походов в Википедию {len(poster.asked)}"
    assert second.read(digest) == (POSTER, "image/jpeg")


@pytest.mark.machine
def test_one_poster_serves_the_whole_series(tmp_path: Path) -> None:
    """Постер у сериала один на все серии, а вот кадр - свой у каждой.

    Поэтому полка знает картину без подписи серии: следующая серия берёт её постер, не
    спрашивая Википедию заново.
    """
    poster, frame = FakePoster(), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)

    _settled(made, _film("Уэнздей", 2022, "s1e1"), want=POSTER)
    _settled(made, _film("Уэнздей", 2022, "s1e2"), want=POSTER)

    assert poster.asked == [("Уэнздей", 2022, "tv")], f"спрошено {poster.asked}"


@pytest.mark.machine
def test_a_miss_does_not_become_a_drumbeat_on_wikipedia(tmp_path: Path) -> None:
    """Карточку опрашивают раз в несколько секунд весь показ.

    Без отсрочки каждый такой опрос уезжал бы в Википедию заново - ровным стуком на весь
    фильм, и 429 был бы не случайностью, а расписанием.
    """
    poster, frame = FakePoster(body=None), FakeFrame(body=None)
    made, _ = _posters(poster, frame, tmp_path)
    shown = _film()

    _settled(made, shown)
    for _ in range(20):
        made.picture(shown, lambda: STREAM)
    time.sleep(0.05)

    assert len(poster.asked) == 1, f"походов в Википедию {len(poster.asked)}"


@pytest.mark.machine
def test_only_one_worker_walks_for_one_show(tmp_path: Path) -> None:
    """Опросов много, поход один: иначе за постером ушла бы толпа одинаковых потоков."""
    gate = threading.Event()
    poster, frame = FakePoster(gate=gate), FakeFrame(body=None)
    made, _ = _posters(poster, frame, tmp_path)
    shown = _film()

    try:
        for _ in range(10):
            assert made.picture(shown, lambda: STREAM) == ("", "")
    finally:
        gate.set()
    _settled(made, shown)

    assert len(poster.asked) == 1, f"походов {len(poster.asked)}"


def test_nothing_playing_asks_for_nothing(tmp_path: Path) -> None:
    """Показа нет - и картинки нет: за постером пустоты никто не ходит."""
    poster, frame = FakePoster(), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)

    assert made.picture(None, lambda: STREAM) == ("", "")
    assert made.picture(_film(""), lambda: STREAM) == ("", "")
    assert poster.asked == []


@pytest.mark.machine
def test_a_stranger_name_is_not_served(tmp_path: Path) -> None:
    """🔴 Имя приезжает снаружи: собранный из него путь - это чужой файл на диске серва.

    Ищется имя среди готовых картинок, поэтому чужому отвечать нечем.
    """
    made, _ = _posters(FakePoster(), FakeFrame(), tmp_path)
    _settled(made, _film())

    assert made.read("../../etc/passwd") is None
    assert made.read("") is None


def test_the_same_door_serves_the_pictures_of_the_found_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Маршрут картинок у серва один, и список находок ходит в ту же дверь.

    Имена у находок свои (:class:`hass.hit_posters.HitPosters`), но второго маршрута
    наружу под них не заводится: спросили тем же адресом - отдалась та же картинка.
    """
    found = HitPosters(
        source=FakeSource(body=OTHER), shelf=PosterShelf(home=lambda: tmp_path / "posters")
    )
    monkeypatch.setattr("hass.posters.hits", found)
    offered = found.offer([{"pick": 1, "title": "Тачки", "year": 2006, "kind": "movie"}])[0]
    assert isinstance(offered, dict)
    made, _ = _posters(FakePoster(), FakeFrame(), tmp_path)

    assert made.read(str(offered["poster"])) == (OTHER, "image/jpeg")


@pytest.mark.machine
def test_the_last_pictures_stay_and_the_oldest_leaves(tmp_path: Path) -> None:
    """Готовых держим несколько: карточка ещё тянет прошлую, когда показ уже сменился."""
    poster, frame = FakePoster(), FakeFrame()
    made, _ = _posters(poster, frame, tmp_path)
    digests: list[str] = []

    for number in range(6):
        poster.body = f"picture {number}".encode()
        want = poster.body
        digests.append(_settled(made, _film(f"Картина {number}", 2000 + number), want=want)[1])

    assert made.read(digests[-1]) is not None
    assert made.read(digests[0]) is None, "самая старая картинка уступила место новым"


def test_by_default_the_poster_is_looked_for_in_both_real_sources() -> None:
    """🔴 Собранный по умолчанию источник - настоящий, а не двойник соседней пробы.

    Каждая проверка выше подставляет свой источник, и подмени сборка настоящий поход на
    пустой ответ - красным не стало бы НИЧЕГО: карточка молча показывала бы запасной
    кадр всю жизнь, а «постера не нашлось» выглядело бы честным ответом.

    Клиент тут тот же, каким ходит справка: та же память адресов, тот же именной
    `User-Agent`, тот же проверенный TLS - и ни одного нового хоста наружу.
    """
    made = Posters()
    found = made._poster
    source = getattr(found, "__self__", None)

    assert isinstance(source, BothPosters), "по умолчанию за постером идут оба источника"
    assert isinstance(source.first, WikiPoster), "первой отвечает Википедия"
    assert isinstance(source.second, ImdbPoster), "молчащих добирает IMDb"
    assert found.__name__ == "poster"
    assert source.first.client is FACTS.client
    assert source.first.files is FACTS.client
    assert source.second.client is FACTS.client
    assert made._frame is frame_shot, "запасной путь тоже собран настоящим"


@pytest.mark.machine
def test_the_frame_is_taken_again_until_the_stream_opens(tmp_path: Path) -> None:
    """🔴 Показ объявляется играющим РАНЬШЕ, чем ffmpeg может прочитать его манифест.

    Живой замер на стенде: карточку опрашивают со 2 с показа, а сетка раздачи
    открывается на 4.3 с. Единственная попытка приходилась ровно в эту щель и
    промахивалась - а второй ей взяться было неоткуда: постер к тому времени уже
    промахнулся и отложил себя, и карточка стояла пустой ВЕСЬ показ (118 с замера).
    """
    poster, frame = FakePoster(body=None), LateFrame()
    made, _ = _posters(poster, frame, tmp_path)

    address, digest = _settled(made, _film(), want=FRAME)

    assert address == ROUTE + digest, "карточке достался кадр, а не пустота"
    assert made.read(digest) == (FRAME, "image/jpeg")
    assert len(frame.asked) > 1, f"кадр пробовали {len(frame.asked)} раз, а не снова"
