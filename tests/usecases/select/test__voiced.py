"""Зеркало ``--voice``: у поднятой раздачи есть хозяин, и бесхозной она не остаётся."""

from __future__ import annotations

import pytest

import torrcast.usecases.select._pick_state as pick_state
import torrcast.usecases.select._voiced as voiced_module
from tests.fakes.composition import use_rank_console
from tests.fakes.console import FakeConsole
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.usecases.rank.releases import media, track
from tests.usecases.select.world import entry
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.media import Media
from torrcast.domain.rank_settings import VOICE_MENU
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.select._voiced import _Voiced, _voiced
from torrcast.usecases.torrent_claims import CLAIMS


class _Dropped:
    """Кто и что снёс: подделке отбора хватает списка хэшей."""

    def __init__(self, fails: bool = False) -> None:
        self.calls: list[list[str]] = []
        self._fails = fails

    def __call__(self, config: Config, hashes: list[str]) -> None:
        self.calls.append(list(hashes))
        if self._fails:
            raise TorrcastError("служба раздач не отвечает")


def test_without_the_flag_nothing_is_read_at_all() -> None:
    """Флага нет - этот путь тем и хорош, что обходится состоянием без похода в рой."""
    saved = entry(voice="Дубляж")

    assert _voiced(Config(), saved, Args(query=["кино"])) is saved


def test_a_torrent_handed_to_the_show_is_not_taken_away() -> None:
    """Юнит играет тот же магнит - раздача его, и убирать её тут нельзя."""
    own = _Voiced(torrent_hash="a" * 40, handed=True)
    dropped = _Dropped()

    own.drop(Config(), dropped)

    assert dropped.calls == []


def test_a_torrent_nobody_took_is_removed_by_its_own_hash() -> None:
    """Сухой прогон, Ctrl-C, «серии тут нет» - во всех исходах раздача убирается."""
    own = _Voiced(torrent_hash="b" * 40)
    dropped = _Dropped()

    own.drop(Config(), dropped)

    assert dropped.calls == [["b" * 40]]


def test_dropping_twice_is_harmless() -> None:
    """Повторный вызов и пустой хэш безвредны: чужого он не касается."""
    own = _Voiced(torrent_hash="c" * 40)
    dropped = _Dropped()

    own.drop(Config(), dropped)
    own.drop(Config(), dropped)

    assert dropped.calls == [["c" * 40]]
    assert own.torrent_hash == ""


def test_a_service_that_refuses_does_not_break_the_way_out() -> None:
    """Служба не отвечает - это не повод уронить выход из команды."""
    own = _Voiced(torrent_hash="d" * 40)

    own.drop(Config(), _Dropped(fails=True))

    assert own.torrent_hash == ""


class _CardLookup:
    """Разбор серий карточки, который держит ту же раздачу в этом процессе."""


def test_a_torrent_the_card_lookup_still_holds_is_left_to_it() -> None:
    """Проверка записи и разбор карточки подняли одну раздачу: снос оставляется последнему."""
    card = _CardLookup()
    own = _Voiced()
    CLAIMS.claim("c" * 40, card)
    CLAIMS.claim("c" * 40, own)
    own.torrent_hash = "c" * 40
    dropped = _Dropped()

    own.drop(Config(), dropped)

    assert dropped.calls == []
    assert CLAIMS.unclaim("c" * 40, card) is True


def test_a_torrent_held_only_by_its_own_check_is_still_removed() -> None:
    """Своя отметка держателя не держит: иначе каждая проверка записи оставляла раздачу."""
    own = _Voiced()
    CLAIMS.claim("d" * 40, own)
    own.torrent_hash = "d" * 40
    dropped = _Dropped()

    own.drop(Config(), dropped)

    assert dropped.calls == [["d" * 40]]


_FILES = [
    TorrFile(index=0, name="Erin - 01.mkv", size=700),
    TorrFile(index=1, name="Sound/Erin - 01.mka", size=100),
]


@pytest.fixture
def probed(monkeypatch: pytest.MonkeyPatch, _russian_product: None) -> dict[str, Media]:
    """Паспорт по адресу потока; раздача своя и сносится в никуда."""
    engine = FakeTorrentEngine(torrent_files=list(_FILES))
    passports: dict[str, Media] = {}
    monkeypatch.setattr(pick_state, "_select_engines", lambda url: engine)
    monkeypatch.setattr(pick_state, "_select_prober", lambda url, timeout: passports[url])
    monkeypatch.setattr(voiced_module, "_held_by_show", lambda torrent_hash: False)
    monkeypatch.setattr(voiced_module, "_release_torrents", lambda config, hashes: None)
    return passports


def test_a_voice_apart_is_read_from_its_own_file(probed: dict[str, Media]) -> None:
    """У пака со звуком рядом видео держит одну ``eng``: rus живёт только в mka."""
    probed["http://fake/hash/0"] = media(tracks=(track(0, "eng", None),))
    probed["http://fake/hash/1"] = media(tracks=(track(0, "eng", None), track(1, "rus", None)))

    played = _voiced(Config(), entry(voiced_apart=True), Args(query=["кино"], voice="rus"))

    assert played.audio == 1


def test_a_studio_of_the_release_names_a_bare_track(probed: dict[str, Media]) -> None:
    """Голые rus сезонного пака называют студии из имени раздачи, записанные в запись."""
    probed["http://fake/hash/0"] = media(tracks=(track(0, "rus", None), track(1, "rus", None)))
    saved = entry(studios=["The Kitchen Russia", "Good People"])

    played = _voiced(Config(), saved, Args(query=["кино"], voice="Good People"))

    assert (played.audio, played.studio) == (1, "Good People")


def test_the_menu_offers_the_own_track_of_a_native_picture(
    probed: dict[str, Media], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Меню озвучек картины своего языка по умолчанию ставит её дорожку, а не дубляж."""
    use_rank_console(monkeypatch, FakeConsole())
    probed["http://fake/hash/0"] = media(tracks=(track(0, "rus", "Дубляж"), track(1, "rus", None)))

    played = _voiced(Config(), entry(native=True), Args(query=["кино"], voice=VOICE_MENU))

    assert played.audio == 1
