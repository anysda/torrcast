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

from tests.fakes import composition
from tests.test_cli import _FakeTorrServer, _plan, _probes, _resolve, rel
from torrcast import InfraError, NotFoundError, SwarmError
from torrcast.adapters.stream_probe.run_ffprobe import _run_ffprobe
from torrcast.adapters.stream_probe.swarm_pulse import swarm_pulse
from torrcast.adapters.torrserver.torr_server import META_STEP_MAX, TorrServer
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.pick_settings import MAX_TRIES, META_BUDGET, PROBE_BUDGET
from torrcast.domain.rank_settings import PEER_GRACE, STEP_GRACE
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.warm_open import KEYS_KEPT
from torrcast.usecases.rank.peer_grace import peer_grace
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import _waiting_note
from torrcast.usecases.select_bench.bench import Bench

if TYPE_CHECKING:
    from pathlib import Path


def test_run_ffprobe_returns_the_moment_the_probe_exits() -> None:
    """Живой релиз не ждёт бюджета: как только ffprobe вышел, отдаём его вывод."""
    began = time.monotonic()
    out = _run_ffprobe(["printf", "hello"], timeout=40.0, alive=lambda: True)
    assert out == "hello"
    assert time.monotonic() - began < 2.0


def test_run_ffprobe_bails_at_once_on_a_swarm_declared_dead() -> None:
    """Рой признан мёртвым — обрываем ffprobe сразу, а не досиживаем весь timeout."""
    began = time.monotonic()
    with pytest.raises(InfraError, match="рой молчит"):
        _run_ffprobe(["sleep", "40"], timeout=40.0, alive=lambda: False)
    assert time.monotonic() - began < 3.0


def test_run_ffprobe_keeps_the_full_budget_while_the_stream_is_alive() -> None:
    """Пока поток жив, бюджет тратится полностью и таймаут остаётся прежним."""
    began = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        _run_ffprobe(["sleep", "40"], timeout=0.5, alive=lambda: True)
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
    composition.use_swarm_grace(monkeypatch, 0.3)

    def read(url: str, timeout: float = 90.0, alive: Any = None) -> Media:
        if "hash-magnet-r0/" in url:  # верх: рой молчит потоком
            end = time.monotonic() + timeout
            while alive is None or alive():
                if time.monotonic() >= end:
                    raise InfraError("ffprobe не дождался потока")
                time.sleep(0.02)
            raise InfraError("рой молчит - за отсрочку не пришло ни байта потока")
        return Media(3600.0, (), "h264")

    composition.use_prober(monkeypatch, read)

    began = time.monotonic()
    prep = _resolve(Bench(cast(Any, _FakeTorrServer())), ranked)
    elapsed = time.monotonic() - began

    printed = capsys.readouterr().out
    assert prep.number == 2, "молчащий поток не останавливает показ"
    assert "релиз 1 не годится (рой молчит" in printed and "беру 2" in printed
    assert elapsed < PROBE_BUDGET, "не сожгли весь бюджет на молчащем релизе"


def test_dead_torrserver_stops_before_the_next_release() -> None:
    """Мёртв общий порт - отказ инфраструктуры, а не три якобы мёртвых роя."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]

    class _Dead(_FakeTorrServer):
        calls = 0

        def add(self, magnet: str) -> str:
            self.calls += 1
            raise ServerDownError(
                "TorrServer не отвечает (http://127.0.0.1:8090): connection refused"
            )

    torrserver = _Dead()
    with pytest.raises(InfraError) as caught:
        _resolve(Bench(cast(Any, torrserver)), ranked)

    assert str(caught.value) == (
        "TorrServer не отвечает (http://127.0.0.1:8090): connection refused"
    )
    assert torrserver.calls <= MAX_TRIES, (
        "параллельная тройка уже могла стартовать, но дальше неё общий отказ не идёт"
    )


def test_the_same_words_without_the_type_do_not_stop_the_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-281. Те же слова, но НЕ типом «служба умерла» - отказ одного релиза.

    Раньше «умерло наше звено» опознавалось по ПРЕФИКСУ строки, которую мы правим
    языком зрителя: стоило тексту измениться - и очередь пошла бы через мёртвый порт
    молча, ни один тест бы не заметил (они проверяли ту же строку). Теперь решает
    тип исключения, и чужая ошибка с теми же словами очередь не останавливает.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(2)]

    class _Shaky(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            if magnet == "magnet-r0":  # слова те же, что у мёртвой службы, а тип - нет
                raise InfraError(
                    "TorrServer не отвечает (http://127.0.0.1:8090): connection refused"
                )
            return super().add(magnet)

    def read(url: str, timeout: float = 90.0, alive: Any = None) -> Media:
        return Media(3600.0, (), "h264")

    composition.use_prober(monkeypatch, read)

    prep = _resolve(Bench(cast(Any, _Shaky())), ranked)

    assert prep.number == 2, "чужая ошибка с теми же словами - не отказ инфраструктуры"


# --- Шаг опроса метаданных (TC-126) ---------------------------------------------------
#
# Ожидание метаданных устранить нельзя: TorrServer не отдаст ни байта, пока рой их не
# привезёт. Устранима только наша добавка к нему - остаток шага опроса. С прежней
# секундой она была видна в замерах глазами: все времена ожидания выходили почти целыми
# (2.01, 3.01, 5.01, 8.02, 11.02, 12.02 с), то есть в среднем полсекунды на каждом
# старте мы досыпали уже поверх готовых метаданных.


class _Late(TorrServer):
    """Клиент TorrServer, у которого метаданные приезжают в назначенный момент времени.

    Именно по времени, а не «на N-м опросе»: шаг опроса как раз и меняет число опросов,
    и счётчик мерил бы не то. Единственный поход по сети подменён, остальной
    :meth:`~torrcast.adapters.torrserver.torr_server.TorrServer.wait_files` живой.

    ``peers`` - что служба отвечает про рой: ``None`` значит «не сказала ничего», и это
    не то же самое, что «пиров нет» (:func:`~torrcast.domain.swarm_alive.swarm_alive`).
    """

    def __init__(self, ready_after: float, peers: int | None = None) -> None:
        super().__init__("http://torrserver.invalid")
        self.ready = time.monotonic() + ready_after
        self.peers = peers
        self.polls = 0

    def status(self, torrent_hash: str) -> dict[str, Any]:
        self.polls += 1
        about: dict[str, Any] = {} if self.peers is None else {"active_peers": self.peers}
        if time.monotonic() < self.ready:
            return about
        return {**about, "file_stats": [{"id": 0, "path": "film.mkv", "length": 8 << 30}]}


def test_metadata_are_taken_up_within_a_step_not_within_a_second() -> None:
    """Пришедшие метаданные ждут нас не дольше одного шага опроса.

    Это и есть цена вопроса: показ стартует настолько позже роя, насколько крупен шаг.
    """
    client = _Late(0.3)
    began = time.monotonic()
    assert client.wait_files("hash", timeout=5.0), "метаданные всё-таки приехали"
    late = time.monotonic() - began - 0.3
    assert late <= META_STEP_MAX + 0.05, f"метаданные пролежали лишние {late:.2f} с"


def test_the_poll_never_turns_into_a_flood() -> None:
    """Мелкий шаг - не повод долбить TorrServer: частота опроса имеет потолок."""
    client = _Late(0.5)
    client.wait_files("hash", timeout=5.0)
    ceiling = 0.5 / META_STEP_MAX + 4  # +4 - разгон лестницы с мелкого шага
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


# --- Пустой рой отличается от медленного за секунды (TC-140) --------------------------
#
# Отказ был честен и стоил двадцати секунд НА РЕЛИЗ: META_BUDGET доставался одинаково и
# рою, который едет медленно, и рою, которого нет вовсе. Отличить их раньше бюджета нечем
# - кроме одного: служба сама считает свои контакты, и ответ про них приезжает тем же
# опросом, которым берутся файлы. Сиды из выдачи тут не судья ни на знак: они врут в обе
# стороны, и отказ идёт по факту «никто не подключился», а не по обещанию индексера.


def test_a_swarm_with_no_contacts_is_called_empty_within_the_grace() -> None:
    """Контактов ноль и за отсрочку не появилось - ждать некого, отказ приходит сразу."""
    client = _Late(99.0, peers=0)
    began = time.monotonic()
    with pytest.raises(InfraError, match="рой пуст"):
        client.wait_files("hash", timeout=20.0, grace=0.3)
    spent = time.monotonic() - began
    assert spent < 1.0, f"пустой рой стоил {spent:.1f} с вместо отсрочки"


def test_a_slow_but_live_swarm_still_waits_out_the_whole_budget() -> None:
    """Контакты есть, метаданные едут долго - это рой, а не пустота: досиживаем до конца.

    Ради этого случая бюджет и назначен, и отсрочка не имеет права его укоротить.
    """
    client = _Late(0.8, peers=3)
    began = time.monotonic()
    assert client.wait_files("hash", timeout=20.0, grace=0.2), "медленный рой всё-таки приехал"
    spent = time.monotonic() - began
    assert spent >= 0.8, f"дождались за {spent:.2f} с - отсрочка укоротила живой рой"


def test_silence_about_peers_is_not_silence_of_the_swarm() -> None:
    """Служба про пиров не сказала ничего - ждём полный бюджет, как ждали всегда.

    Молчание счётчика и отсутствие роя - разные вещи, и путать их нельзя: иначе первая
    же версия TorrServer, назвавшая счётчики иначе, похоронила бы весь отбор.
    """
    client = _Late(99.0, peers=None)
    began = time.monotonic()
    with pytest.raises(InfraError, match="не отдала метаданные"):
        client.wait_files("hash", timeout=0.6, grace=0.2)
    spent = time.monotonic() - began
    assert spent >= 0.6, f"ждали {spent:.2f} с - отказали за неизвестное, а не за известное"


def test_a_healthy_release_pays_nothing_for_the_grace() -> None:
    """Метаданные уже здесь - проверка контактов не случается вовсе, даже на нулевых.

    Здоровая раздача отвечает первым же опросом, то есть до всякой отсрочки, и никакой
    новой миллисекунды на её пути нет.
    """
    client = _Late(0.0, peers=0)
    began = time.monotonic()
    assert client.wait_files("hash", timeout=20.0, grace=0.001), "метаданные были готовы"
    spent = time.monotonic() - began
    assert spent < 0.2, f"готовые метаданные стоили {spent:.2f} с"


def test_swarm_alive_counts_contacts_and_not_addresses_from_dht() -> None:
    """Найденный в DHT адрес - ещё не рой; жизнью считается состоявшийся контакт.

    Ответы взяты с живой службы: свежедобавленная раздача с мёртвым роем минутами
    рапортует ``total_peers`` 7-9 и столько же ``half_open_peers``, а ключей про
    состоявшийся контакт у неё нет вовсе. Считай мы кандидатов жизнью, отсрочка не
    сработала бы ни разу, и отказ по-прежнему стоил бы полный бюджет.
    """
    from torrcast.domain.json_value import JsonValue
    from torrcast.domain.swarm_alive import swarm_alive

    dead: dict[str, JsonValue] = {
        "stat": 1,
        "stat_string": "Torrent getting info",
        "total_peers": 9,
        "half_open_peers": 9,
    }
    live: dict[str, JsonValue] = {
        "stat": 3,
        "stat_string": "Torrent working",
        "total_peers": 379,
        "pending_peers": 378,
        "half_open_peers": 8,
        "active_peers": 1,
        "connected_seeders": 1,
        "bytes_written": 1735,
        "bytes_read": 25635,
    }
    assert swarm_alive(dead) is False, "кандидаты из DHT - не контакт"
    assert swarm_alive(live) is True, "подключённый пир и прочитанные байты - контакт"
    assert swarm_alive({"active_peers": 0, "bytes_read": 4096}) is True
    assert swarm_alive({"active_peers": 0, "total_peers": 0, "download_speed": 0}) is False
    # Служба про рой не рассказала вовсе - ждём полный бюджет, как ждали всегда.
    assert swarm_alive({"file_stats": [], "torrent_size": 8 << 30}) is None


class _Offline(TorrServer):
    """Клиент службы без сети: хэш берётся из магнита, снос копится списком.

    Что именно отвечает раздача - дело наследника: тут проверяется отбор, а не разбор
    JSON, и ответ службы задаётся одним методом :meth:`status`.
    """

    def __init__(self) -> None:
        super().__init__("http://torrserver.invalid")
        self.dropped: list[str] = []

    def add(self, magnet: str) -> str:
        return f"hash-{magnet}"

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)

        return True


class _Empty(_Offline):
    """Раздача пуста: контактов ноль и метаданных не будет никогда."""

    def status(self, torrent_hash: str) -> dict[str, Any]:
        return {"file_stats": [], "active_peers": 0, "total_peers": 0, "download_speed": 0}


class _Slow(_Offline):
    """Рой медленный, но живой: пиры есть с первой секунды, метаданные едут позже."""

    def __init__(self, ready_after: float, peers: int) -> None:
        super().__init__()
        self.ready = time.monotonic() + ready_after
        self.peers = peers

    def status(self, torrent_hash: str) -> dict[str, Any]:
        about: dict[str, Any] = {"active_peers": self.peers}
        if time.monotonic() < self.ready:
            return about
        return {**about, "file_stats": [{"id": 0, "path": "film.mkv", "length": 8 << 30}]}


def test_prewarm_cannot_judge_the_swarm_before_the_release_is_chosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Часы первого контакта не тикают, пока человек читает меню."""
    ranked = [rel(name="полный", quality="1080p")]
    composition.use_graces(monkeypatch, peer=0.15)
    bench = Bench(cast(Any, _Empty()), meta_budget=1.0)
    plan = _plan(ranked)

    prep = bench.start(plan, 1)
    time.sleep(0.25)
    assert not prep.ready.is_set(), "прогрев вынес приговор до выбора"

    bench._ask(plan, prep, [1])
    assert prep.ready.wait(0.5), "после выбора обычная отсрочка не сработала"
    assert isinstance(prep.failure, SwarmError)


def test_a_picture_whose_swarm_never_answers_is_refused_in_seconds_with_a_move(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Вся очередь молчит пирами - правда говорится быстро и с ходом для человека.

    Сиды у раздач числятся (4, 2 и 1), и заранее их никто не судит: очередь проходится
    целиком, каждая раздача спрашивается по-настоящему. Отказывает факт - служба не
    насчитала ни одного контакта, - а не обещание индексера.

    🔴 TC-300. Цена отказа теперь складывается из двух разных вещей, и обе тут проверяются:
    сам обход очереди по-прежнему стоит отсрочек, а не бюджетов (три раздачи - меньше
    секунды), но сверх него платится РОВНО ОДИН полный бюджет раздачи - за последний,
    терпеливый спрос лучшей из промолчавших (:meth:`~torrcast.cli.Bench._recheck`). Трёх
    бюджетов, как до отсрочек, тут нет и близко.
    """
    ranked = [rel(name=f"r{i}", seeders=4 - i) for i in range(3)]
    composition.use_graces(monkeypatch, peer=0.3)
    torrserver = _Empty()

    began = time.monotonic()
    with pytest.raises(NotFoundError) as refusal:
        _resolve(Bench(cast(Any, torrserver)), ranked)
    spent = time.monotonic() - began

    said = str(refusal.value)
    printed = capsys.readouterr().out
    assert spent < META_BUDGET * 1.25, (
        f"отказ занял {spent:.1f} с: обход трёх раздач стоит отсрочек, а сверх него - "
        "один бюджет раздачи на терпеливый спрос, но не три бюджета"
    )
    assert printed.count("не дождались") == 3, "каждая осечка называет предел ожидания"
    assert "спрашиваю релиз 1 ещё раз" in printed, "последний спрос тоже громкий"
    assert "потрогали 3 (все)" in said, "спросили не всю очередь"
    assert "ни одна не отозвалась" in said and "числятся" in said
    assert "назови картину иначе" in said, "отказ без хода - тупик"
    assert torrserver.dropped, "пустые раздачи из TorrServer убираются"


def test_a_slow_swarm_is_not_mistaken_for_an_empty_one_by_the_pick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Верх едет медленно, но пиры у него есть - отбор дожидается его и играет именно его.

    Обратная сторона той же правки: ускорять отказ можно только там, где отказывать не
    жалко. Живой рой обязан доехать, сколько бы отсрочек мимо него ни прошло.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    composition.use_graces(monkeypatch, peer=0.2)

    def read(url: str, timeout: float = 90.0, alive: Any = None) -> Media:
        return Media(3600.0, (), "h264")

    composition.use_prober(monkeypatch, read)

    prep = _resolve(Bench(cast(Any, _Slow(0.6, peers=2))), ranked)

    assert prep.number == 1, "медленный, но живой рой отбор бросать не имеет права"
    assert prep.meta >= 0.6, f"метаданные пришли за {prep.meta:.2f} с - ждали не рой"


# --- Потолок кэшей карт и паспортов (TC-127) ------------------------------------------
#
# Карта опорных кадров снимается у роя (первое чтение хвоста стоит 13-24 с), и полка
# существует ровно затем, чтобы не платить рою второй раз. Но потолка у неё не было
# вовсе: на живой полке 299 карт весят 8.7 МБ (медиана 22 КБ, самая большая - 874 КБ), и
# на инструменте, который работает годами, это тихий рост диска без единой строки наружу.


def _fake_map() -> Any:
    """Снятие карты без роя и без файла: тут проверяется полка, а не разбор Cues."""
    from torrcast.domain.frames import keymap as keymap_mod

    def keyframes(_: str) -> Any:
        return keymap_mod.KeyMap(60.0, (keymap_mod.Point(0.0, 0, 0),), 0, 0, "mkv")

    return keyframes


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
    from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
    from torrcast.adapters.stream_pack.film_keys import film_keys

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    keys_of = _fake_map()

    for number in range(8):  # полка ровно под потолок, и вся она «старая»
        film_keys(_url(number), keys_of=keys_of, kept=8)
        os.utime(_keys_cache(_url(number)), (number, number))
    got = film_keys(_url(0), keys_of=keys_of, kept=8)
    assert got.duration == 60.0, "старейшую карту взяли с полки"

    for number in range(100, 104):  # четыре новых фильма выдавливают полку за потолок
        film_keys(_url(number), keys_of=keys_of, kept=8)
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
    from torrcast.adapters.stream_probe.media_shelf import _keep_media, _media_cache, _read_media

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    passport = Media(3600.0, (AudioTrack(0, "rus", "", "aac", 2),), "h264")

    # Потолок полки держит та же запись паспорта, которую здесь и зовут.
    for number in range(8):
        _keep_media(_media_cache(_url(number)), passport, kept=8)
        os.utime(_media_cache(_url(number)), (number, number))
    assert _read_media(_media_cache(_url(0))) is not None, "старейший паспорт спросили"

    for number in range(100, 104):
        _keep_media(_media_cache(_url(number)), passport, kept=8)
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
    from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
    from torrcast.adapters.stream_pack.film_keys import film_keys

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    keys_of = _fake_map()

    cache = _keys_cache(_url(0))
    cache.parent.mkdir(parents=True, exist_ok=True)
    alien = cache.parent / "чужое.lock"
    alien.write_text("не наше дело", "utf-8")
    for junk in ('{"duration": 60.0, "keys": [0.0, 1', "", '{"keys": []}', "[1, 2, 3]"):
        cache.write_text(junk, "utf-8")
        got = film_keys(_url(0), keys_of=keys_of, kept=4)
        assert got.duration == 60.0, f"мусор {junk!r} уронил старт"
        assert cache.read_text("utf-8") != junk, "мусор перезаписан снятой картой"

    for number in range(20):  # подрезка обязана пережить мусор рядом
        cache.with_name(f"{number:016x}.json").write_text("не json", "utf-8")
        film_keys(_url(number + 1), keys_of=keys_of, kept=4)
    assert alien.exists(), "подрезка тронула чужой файл"


def test_trimming_does_not_hold_up_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Подрезка идёт в общей нитке с показом, поэтому её цена названа числом.

    Полная полка, худший случай - тот показ, на котором подрезка и случается: он платит
    полный обход со ``stat``. Всё остальное время это один ``scandir``.
    """
    from torrcast.adapters.stream_pack._keys_shelf import _keys_cache
    from torrcast.adapters.stream_pack.film_keys import film_keys
    from torrcast.adapters.stream_probe.shelf import _trim

    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    keys_of = _fake_map()
    film_keys(_url(0), keys_of=keys_of)
    shelf = _keys_cache(_url(0)).parent
    for number in range(KEYS_KEPT + 1):
        (shelf / f"{number:016x}.json").write_text("{}", "utf-8")

    began = time.monotonic()
    _trim(shelf, KEYS_KEPT)  # перебор потолка: полный обход и удаление
    worst = time.monotonic() - began
    began = time.monotonic()
    _trim(shelf, KEYS_KEPT)  # полка под потолком: один scandir
    usual = time.monotonic() - began
    assert worst < 0.1, f"подрезка полной полки стоила {worst * 1000:.1f} мс"
    assert usual < 0.02, f"обычная проверка полки стоила {usual * 1000:.1f} мс"


class _LateHead(_Offline):
    """Верх очереди отзывается позже отсрочки, остальные - сразу.

    Так выглядит обычная раздача в неудачную минуту: контактов на первых секундах нет,
    служба рапортует одних кандидатов из DHT, а потом рой находится и метаданные едут.
    """

    def __init__(self, head: str, answers_in: float) -> None:
        super().__init__()
        self.head = head
        self.ready = time.monotonic() + answers_in

    def status(self, torrent_hash: str) -> dict[str, Any]:
        files = [{"id": 0, "path": "film.mkv", "length": 8 << 30}]
        if torrent_hash != self.head:
            return {"active_peers": 3, "file_stats": files}
        if time.monotonic() < self.ready:
            return {"active_peers": 0, "total_peers": 8, "half_open_peers": 8}
        return {"active_peers": 2, "file_stats": files}


def test_the_grace_a_release_gets_is_the_price_of_dropping_it() -> None:
    """Длинная отсрочка достаётся тому, чьей осечкой платят ступенью чёткости.

    🔴 TC-387. Терпение тут не про раздачу, а про то, чем обходится ошибка: под 1080p с
    720p в очереди стоит обещание продукта, а под 720p - соседнее место в очереди.
    """
    full, hd = rel(name="полный", quality="1080p"), rel(name="обычный", quality="720p")
    quiet = rel(name="молчит про кадр", quality=None)
    twin = rel(name="второй", quality="1080p")
    four_k = rel(name="четыре кэ", quality="2160p")

    assert peer_grace(_plan([full, hd]), 1, [1, 2]) == STEP_GRACE
    assert peer_grace(_plan([full, quiet]), 1, [1, 2]) == STEP_GRACE, (
        "имя, молчащее о разрешении, ступень не обещает - защищать её есть от кого"
    )
    assert peer_grace(_plan([full, twin]), 1, [1, 2]) == PEER_GRACE, (
        "заменить ступенью ниже нечем - терпение ничего не защищает"
    )
    assert peer_grace(_plan([full, hd]), 2, [1, 2]) == PEER_GRACE
    assert peer_grace(_plan([four_k, hd]), 1, [1, 2]) == STEP_GRACE, (
        "2160p - тоже честный HD, и ступень под ним та же"
    )


def test_grace_follows_the_actual_route_and_only_the_untried_tail() -> None:
    """Длинное ожидание защищает ступень только в фактической очереди захода."""
    full = rel(name="полный", quality="1080p")
    judged = rel(name="осуждённый", quality="720p")
    sound = rel(name="сосед по звуку", quality="1080p")
    lower = rel(name="запасной", quality="720p")
    plan = _plan([full, judged, sound, lower])

    assert peer_grace(plan, 1, [1, 2, 3, 4]) == STEP_GRACE
    assert peer_grace(plan, 1, [1]) == PEER_GRACE, "--release N"
    assert peer_grace(plan, 3, [3]) == PEER_GRACE, "вопрос про звук"
    assert peer_grace(plan, 1, [2, 1]) == PEER_GRACE, "осуждённый сосед уже позади"


def test_silence_is_named_as_our_expired_wait() -> None:
    """Ответа роя нет: строка сообщает предел ожидания, а не выдуманный приговор."""
    prep = _Prep(
        number=1,
        release=rel(name="молчун"),
        failure=SwarmError("рой пуст - за 6 с ни одного пира"),
    )

    assert _waiting_note(prep, str(prep.failure)) == "не дождались за 6 с"


def test_a_full_hd_head_is_not_dropped_for_a_slow_minute_of_its_swarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1080p, чей рой отозвался позже обычной отсрочки, играет сам, а не уступает 720p.

    🔴 TC-387. Замер: один и тот же релиз в соседних прогонах то жив, то «рой пуст», и
    от этого зависит ступень на экране.
    """
    ranked = [rel(name="полный", quality="1080p"), rel(name="обычный", quality="720p")]
    prober = _probes(ranked, "h264", "h264")
    composition.use_graces(monkeypatch, peer=0.2)
    composition.use_graces(monkeypatch, step=1.2)
    head = f"hash-{ranked[0].magnet}"

    bench = Bench(cast(Any, _LateHead(head, answers_in=0.6)), prober=prober)
    prep = _resolve(bench, ranked)

    assert prep.number == 1, "ступень отдали не рою, а собственному нетерпению"
    assert prep.meta >= 0.6, f"метаданные пришли за {prep.meta:.2f} с - ждали не рой"


def test_a_slow_head_still_yields_when_nothing_below_it_is_a_step_lower(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Терпение узкое: очередь из одинаковых ступеней идёт дальше по обычной отсрочке.

    Иначе это была бы не защита ступени, а поднятый всем :data:`~torrcast.cli.PEER_GRACE`,
    и каждый пустой рой снова стоил бы человеку лишних секунд.
    """
    ranked = [rel(name="полный", quality="1080p"), rel(name="второй", quality="1080p")]
    prober = _probes(ranked, "h264", "h264")
    composition.use_graces(monkeypatch, peer=0.2)
    composition.use_graces(monkeypatch, step=1.2)
    head = f"hash-{ranked[0].magnet}"

    bench = Bench(cast(Any, _LateHead(head, answers_in=0.6)), prober=prober)
    prep = _resolve(bench, ranked)

    assert prep.number == 2, "ступени под верхом нет - ждать его дольше незачем"
    assert "не дождались" in capsys.readouterr().out
