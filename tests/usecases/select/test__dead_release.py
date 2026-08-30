"""Зеркало приговора записанной раздаче: что считается «мертво» и что им НЕ считается."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.fakes.journal import Tape
from tests.usecases.select.world import entry
from torrcast.domain.config import Config
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.worker_settings import WORKER_META
from torrcast.usecases.select._dead_release import _dead_release
from torrcast.usecases.select._voiced import _Voiced


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русский приговор записанной раздаче."""

MOVIE = [TorrFile(0, "Кино/Кино.1080p.mkv", 8 * 1024**3), TorrFile(1, "Кино/cover.jpg", 1024)]


class _Swarm:
    """Служба раздач в объёме одного вопроса: жива ли записанная раздача.

    ``needs`` - сколько секунд рою нужно на метаданные: меньше этого срока раздача не
    отвечает вовсе, столько и больше - отдаёт свои файлы. Так подделка отличает медленную
    живую раздачу от мёртвой ровно тем, чем их отличает бой, - бюджетом ожидания.
    """

    def __init__(self, files: list[TorrFile] | None = None, needs: float = 0.0) -> None:
        self.files = MOVIE if files is None else files
        self.needs = needs
        self.added: list[str] = []
        self.asked: list[float] = []

    def __call__(self, url: str, timeout: float = 30.0) -> _Swarm:
        return self

    def add(self, magnet: str) -> str:
        self.added.append(magnet)
        return "hash-кино"

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        self.asked.append(timeout)
        if timeout < self.needs:
            raise SwarmError(f"раздача не отдала метаданные за {timeout:.0f} с - нет пиров")
        return list(self.files)


def test_a_release_that_still_holds_the_recorded_file_plays_as_it_played(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Здоровая запись приговора не получает: файл на месте, значит играть есть чем."""
    swarm = _Swarm()
    composition.use_engines(monkeypatch, swarm)

    assert _dead_release(Config(), entry(file_idx=0), _Voiced()) == ""
    assert swarm.added == ["magnet:?xt=кино"], "раздача поднимается один раз"


def test_a_swarm_that_never_answered_is_the_verdict_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Метаданные не приехали за полный бюджет юнита - играть нечего, и это сказано словами."""
    composition.use_engines(monkeypatch, _Swarm(needs=WORKER_META + 1.0))

    assert _dead_release(Config(), entry(), _Voiced()) == (
        f"раздача не отдала метаданные за {WORKER_META:.0f} с - нет пиров"
    )


def test_a_slow_but_living_swarm_is_not_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 Ложный отказ хуже отказа вовсе: медленная живая раздача играет, а не уступает.

    Рою тут нужно 45 с - втрое больше отсрочки «рой пуст» и вдвое больше бюджета
    метаданных под меню (:data:`torrcast.domain.pick_settings.META_BUDGET`), но меньше
    последнего рубежа юнита. Порог, взятый по любому из дешёвых сроков, увёл бы зрителя
    с уже прогретого места на релиз, который надо греть с нуля.
    """
    swarm = _Swarm(needs=45.0)
    composition.use_engines(monkeypatch, swarm)

    assert _dead_release(Config(), entry(file_idx=0), _Voiced()) == ""
    assert swarm.asked == [WORKER_META], "спрашиваем тем же сроком, каким спросит юнит"


def test_a_release_without_the_recorded_file_is_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    """Файла с записанным номером в раздаче больше нет - показывать в ней нечего."""
    composition.use_engines(monkeypatch, _Swarm())

    assert _dead_release(Config(), entry(file_idx=7), _Voiced()) == "файла №7 в ней больше нет"


def test_a_silent_service_is_not_a_verdict_on_the_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Молчит СЛУЖБА, а не раздача: перебирать релизы через мёртвый TorrServer нечем.

    Такой запуск идёт ровно туда же, куда шёл до этой проверки, и о службе скажет сам.
    """

    class _Down(_Swarm):
        def add(self, magnet: str) -> str:
            raise ServerDownError("TorrServer не отвечает")

    composition.use_engines(monkeypatch, _Down())

    assert _dead_release(Config(), entry(), _Voiced()) == ""


def test_the_raised_torrent_gets_an_owner_even_when_it_is_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Раздача, поднятая ради вопроса, не остаётся в службе навсегда: у неё есть хозяин."""
    composition.use_engines(monkeypatch, _Swarm(needs=WORKER_META + 1.0))
    own = _Voiced()

    assert _dead_release(Config(), entry(), own) != ""
    assert own.torrent_hash == "hash-кино"


def test_a_living_release_is_marked_with_its_outcome_and_price(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """Счастливый путь меряется первым: проверка стоит на нём у каждого зрителя каждый раз."""
    composition.use_engines(monkeypatch, _Swarm())

    assert _dead_release(Config(), entry(file_idx=0), _Voiced()) == ""

    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "жива"
    assert mark["секунд"] >= 0.0, "у проверки есть цена числом"


def test_a_buried_release_is_marked_with_the_reason_of_its_death(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """Приговор несёт в след свою причину: по ней мёртвое отличается от молчащего."""
    composition.use_engines(monkeypatch, _Swarm(needs=WORKER_META + 1.0))

    assert _dead_release(Config(), entry(), _Voiced()) != ""

    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "похоронена"
    assert mark["причина"] == f"раздача не отдала метаданные за {WORKER_META:.0f} с - нет пиров"


def test_an_unasked_question_is_not_marked_as_a_living_release(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """🔴 «Спросить не удалось» возвращает пусто, как и «жива», - отметка обязана их различать."""

    class _Down(_Swarm):
        def add(self, magnet: str) -> str:
            raise ServerDownError("TorrServer не отвечает")

    composition.use_engines(monkeypatch, _Down())

    assert _dead_release(Config(), entry(), _Voiced()) == ""

    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "не спрошена", "пустой ответ не должен читаться как «жива»"
