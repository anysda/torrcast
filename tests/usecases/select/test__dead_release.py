"""Зеркало приговора записанной раздаче: что считается «мертво» и что им НЕ считается."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.fakes.journal import Tape
from tests.usecases.select.dead_swarm import Swarm
from tests.usecases.select.world import entry
from torrcast.domain.config import Config
from torrcast.domain.pick_settings import RECORDED_CONTACT
from torrcast.domain.server_down_error import ServerDownError
from torrcast.usecases.select._dead_release import _dead_release
from torrcast.usecases.select._voiced import _Voiced


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русский приговор записанной раздаче."""


def test_a_release_that_still_holds_the_recorded_file_plays_as_it_played(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Здоровая запись приговора не получает: файл на месте, значит играть есть чем."""
    swarm = Swarm()
    composition.use_engines(monkeypatch, swarm)

    assert _dead_release(Config(), entry(file_idx=0), _Voiced()) == ""
    assert swarm.added == ["magnet:?xt=кино"], "раздача поднимается один раз"


def test_a_swarm_that_never_answered_is_the_verdict_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Метаданные не приехали за срок записи - играть нечего, и это сказано словами."""
    composition.use_engines(monkeypatch, Swarm(needs=RECORDED_CONTACT + 1.0))

    assert _dead_release(Config(), entry(), _Voiced()) == (
        f"раздача не отдала метаданные за {RECORDED_CONTACT:.0f} с - нет пиров"
    )


def test_a_slow_swarm_plays_inside_the_limit_and_yields_beyond_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Граница названа числом: 29 с до метаданных - играет, 36 с (самая долгая живая
    запись в замере) - уступает поиску, и место переезжает с ней, а не теряется."""
    slow = Swarm(needs=RECORDED_CONTACT - 1.0)
    composition.use_engines(monkeypatch, slow)
    assert _dead_release(Config(), entry(file_idx=0), _Voiced()) == ""
    assert slow.asked == [RECORDED_CONTACT], "метаданные ждём ровно сроком записи"

    composition.use_engines(monkeypatch, Swarm(needs=36.1))
    assert _dead_release(Config(), entry(file_idx=0), _Voiced()) != ""


def test_a_release_without_the_recorded_file_is_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    """Файла с записанным номером в раздаче больше нет - показывать в ней нечего."""
    composition.use_engines(monkeypatch, Swarm())

    assert _dead_release(Config(), entry(file_idx=7), _Voiced()) == "файла №7 в ней больше нет"


def test_a_silent_service_is_not_a_verdict_on_the_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Молчит СЛУЖБА, а не раздача: перебирать релизы через мёртвый TorrServer нечем.

    Такой запуск идёт ровно туда же, куда шёл до этой проверки, и о службе скажет сам.
    """

    class _Down(Swarm):
        def add(self, magnet: str) -> str:
            raise ServerDownError("TorrServer не отвечает")

    composition.use_engines(monkeypatch, _Down())

    assert _dead_release(Config(), entry(), _Voiced()) == ""


def test_the_raised_torrent_gets_an_owner_even_when_it_is_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Раздача, поднятая ради вопроса, не остаётся в службе навсегда: у неё есть хозяин."""
    composition.use_engines(monkeypatch, Swarm(needs=RECORDED_CONTACT + 1.0))
    own = _Voiced()

    assert _dead_release(Config(), entry(), own) != ""
    assert own.torrent_hash == "hash-кино"


def test_a_living_release_is_marked_with_its_outcome_and_price(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """Счастливый путь меряется первым: проверка стоит на нём у каждого зрителя каждый раз."""
    composition.use_engines(monkeypatch, Swarm())

    assert _dead_release(Config(), entry(file_idx=0), _Voiced()) == ""

    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "жива"
    assert mark["секунд"] >= 0.0, "у проверки есть цена числом"


def test_an_unasked_question_is_not_marked_as_a_living_release(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """🔴 «Спросить не удалось» возвращает пусто, как и «жива», - отметка обязана их различать."""

    class _Down(Swarm):
        def add(self, magnet: str) -> str:
            raise ServerDownError("TorrServer не отвечает")

    composition.use_engines(monkeypatch, _Down())

    assert _dead_release(Config(), entry(), _Voiced()) == ""

    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "не спрошена", "пустой ответ не должен читаться как «жива»"
