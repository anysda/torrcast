"""Зеркало четвёртого признака мёртвой записи: с роем поговорили, а байта он не отдал."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from tests.fakes import composition
from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from tests.usecases.select.dead_swarm import Swarm
from tests.usecases.select.world import entry
from torrcast.domain.config import Config
from torrcast.domain.pick_settings import RECORDED_CONTACT, SWARM_GRACE
from torrcast.domain.swarm_error import SwarmError
from torrcast.usecases.select._dead_release import _dead_release, _delivered
from torrcast.usecases.select._voiced import _Voiced


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русский приговор записанной раздаче."""


class _Byte:
    """Первый байт записанного файла: что ответит ждалка и о чём и когда её спросили."""

    def __init__(self, said: bool | None, clock: FakeClock) -> None:
        self.said = said
        self.clock = clock
        self.urls: list[str] = []
        self.asked_at: list[float] = []
        self.budgets: list[float] = []

    def __call__(self, url: str) -> Callable[[float], bool | None]:
        self.urls.append(url)
        self.asked_at.append(self.clock.now)

        def arrived(timeout: float) -> bool | None:
            self.budgets.append(timeout)
            return self.said

        return arrived


def _world(
    monkeypatch: pytest.MonkeyPatch,
    said: bool | None,
    talks_at: float = 0.0,
    flows_at: float | None = None,
) -> _Byte:
    clock = FakeClock()
    composition.use_engines(monkeypatch, Swarm(talks_at=talks_at, clock=clock, flows_at=flows_at))
    byte = _Byte(said, clock)
    composition.use_first_byte(monkeypatch, byte)
    return byte


def test_a_swarm_that_talks_but_gives_no_byte_is_buried(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """🔴 TC-1420. Пир отвечает, а содержимое не едет: запись звалась живой, и каждый запуск
    шесть минут сидел без кадра. Теперь - приговор с причиной в строке и в следе."""
    byte = _world(monkeypatch, said=False)
    own = _Voiced()

    verdict = _dead_release(Config(), entry(file_idx=0), own, clock=byte.clock)

    assert verdict.startswith("за ") and verdict.endswith(" с она не отдала ни байта"), verdict
    assert byte.urls == ["http://ts/stream/hash-кино/0"], "спрошен записанный файл, а не любой"
    assert own.torrent_hash == "hash-кино", "поднятую раздачу уберёт тот, кто её поднял"
    (mark,) = tape.named("записанная раздача")
    assert (mark["исход"], mark["причина"]) == ("похоронена", verdict)


def test_a_swarm_that_gives_the_first_byte_plays_as_it_played(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """Байт пришёл - запись жива, приговора нет, след говорит «жива»."""
    byte = _world(monkeypatch, said=True)

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=byte.clock) == ""
    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "жива"


def test_a_service_that_refuses_to_serve_the_file_gives_no_verdict(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """Отказ самой службы - «спросить не удалось», записанное играет как играло."""
    byte = _world(monkeypatch, said=None)

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=byte.clock) == ""
    (mark,) = tape.named("записанная раздача")
    assert (mark["исход"], mark["причина"]) == ("не спрошена", "служба не дала прочитать файл")


def test_the_byte_is_asked_before_the_contact_and_not_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Чтение байта идёт внахлёст с ожиданием контакта: живая запись не платит дважды."""
    byte = _world(monkeypatch, said=True, talks_at=20.0)

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=byte.clock) == ""
    assert byte.asked_at == [0.0], "чтение начато до первого опроса роя"
    assert byte.clock.now >= 20.0, "а приговор вынесен только после контакта"


def test_content_counted_by_the_service_answers_before_the_stream_byte(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """🔴 TC-1420. Служба насчитала полезные байты роя - запись жива, байта потока не ждём.

    Поток отдаёт байт только целым проверенным куском: на стенде это 1.3-2.7 с поверх
    счётчика службы, и каждая живая запись платила их на старте."""
    byte = _world(monkeypatch, said=False, flows_at=1.5)

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=byte.clock) == ""
    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "жива"
    assert byte.clock.now < 2.0, "ждали ровно до счётчика, а не до конца срока"


def _never(_timeout: float) -> bool | None:
    return False


def test_the_content_wait_ends_with_the_contact_limit() -> None:
    """Контакт был ранним - содержимое ждут не дольше срока от ``add``."""
    clock = FakeClock()

    with pytest.raises(SwarmError) as refused:
        _delivered(_never, time.monotonic(), clock=clock)

    assert RECORDED_CONTACT - 1.0 < clock.now <= RECORDED_CONTACT
    assert refused.value.waited == round(RECORDED_CONTACT)


def test_a_late_contact_still_gets_the_grace_for_its_content() -> None:
    """Пир найден на последней секунде срока - содержимому дают отсрочку роя, а не остаток."""
    clock = FakeClock()

    with pytest.raises(SwarmError) as refused:
        _delivered(_never, time.monotonic() - (RECORDED_CONTACT - 0.5), clock=clock)

    assert SWARM_GRACE - 0.5 < clock.now <= SWARM_GRACE
    assert refused.value.waited is not None and refused.value.waited >= RECORDED_CONTACT - 1
