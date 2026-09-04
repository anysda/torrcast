"""Повтор LOAD посреди показа: две попытки, своё место и его исход в недельном следе."""

from __future__ import annotations

from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.cast.reload import _reload
from torrcast.ports.journal import slot as journal_slot


class _Quiet(Wired):
    """Приёмник, у которого LOAD и перезапуск приложения только записываются.

    ``tape`` нужен ради ПОРЯДКА: приёмник запоминает, что лента знала о повторе в тот миг,
    когда повтор ещё делался. Без этого «запись до попытки» от «записи после» не отличить
    ничем - строка в ленте в обоих случаях одна и та же.
    """

    def __init__(self, breaks: bool = False, tape: Tape | None = None, **rest: Any) -> None:
        super().__init__(**rest)
        self.breaks = breaks
        self.tape = tape
        self.told: list[str] | None = None
        self.loads: list[float] = []
        self.restarts = 0

    def _restart_app(self) -> None:
        self.restarts += 1
        if self.tape is not None:
            self.told = self.tape.events()
        if self.breaks:
            raise OSError("приёмник ушёл")

    def _load(self, at: float = 0.0, paused: bool = False) -> None:
        self.loads.append(at)


def _traced(breaks: bool) -> list[dict[str, Any]]:
    """Записи ``reload`` одного и того же сценария; ``breaks`` меняет только ИСХОД."""
    journal_slot.install(tape := Tape())
    receiver = _Quiet(breaks=breaks)
    receiver._peak, receiver._error_code = 1272.4, 905
    _reload(receiver)
    return tape.named("reload")


def test_the_receiver_is_brought_back_exactly_where_it_stumbled(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """Манифест описывает весь фильм, поэтому вернуть приёмник туда - это позиция в LOAD.

    Приложение при этом поднимается чистым: залипший молчит на любой LOAD.
    """
    receiver = _Quiet()
    receiver._peak, receiver._error_code = 1272.4, 905

    assert _reload(receiver) is True
    assert receiver.loads == [1272.4]
    assert receiver.restarts == 1
    assert receiver._reloads == 1
    assert tape.events() == ["reload"]
    assert tape.named("reload")[0]["error"] == 905
    assert "retrying LOAD" in capsys.readouterr().out


def test_the_retries_run_out_and_the_trouble_stops_being_ours(
    tape: Tape,
) -> None:
    """Ровно столько попыток, сколько разрешает профиль: дальше это не наша авария."""
    receiver = _Quiet()
    receiver._reloads = receiver.profile.load_retries

    assert _reload(receiver) is False
    assert receiver.loads == []


def test_a_show_on_the_viewers_pause_is_not_started_over_by_a_retry(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """Паузу ставил зритель, и смерть сессии её не отменяет: LOAD с автостартом не идёт.

    Живой замер 25-08-2026 на приставке: под голоданием упаковки она убила медиасессию
    сама через 29 с после паузы зрителя, и смерть пришла словом ``IDLE/ERROR``. Повтор
    LOAD перехватывал её раньше круга опроса и начинал фильм поверх паузы.
    """
    receiver = _Quiet()
    receiver._peak, receiver._paused = 1272.4, True

    assert _reload(receiver) is False
    assert receiver.loads == [], "показ, начатый поверх зрительской паузы, - брак"
    assert receiver.restarts == 0
    assert receiver._reloads == 0, "запас повторов остаётся настоящей смерти"
    assert tape.events() == []
    assert capsys.readouterr().out == ""


def test_a_receiver_that_left_mid_retry_is_left_to_the_next_tick(
    tape: Tape,
) -> None:
    """Приёмник мог просто уйти - решает следующий тик, а не исключение из сторожа.

    Но уход этот обязан быть НАЗВАН: молча вернуть ``False`` значит оставить ленту с
    обещанием повтора, которого не было.

    🔴 Слово отказа общее с подъёмом и перезабором - ``упал:``. Завести живому повтору своё
    значило бы развести словари трактов: замер читает исход одним разбором, и второго слова
    для той же аварии он просто не найдёт.
    """
    receiver = _Quiet(breaks=True)
    receiver._peak = 100.0

    assert _reload(receiver) is False

    (record,) = tape.named("reload")
    assert record["ok"] is False
    assert str(record["why"]).startswith("crashed:"), f"чужое слово: {record}"
    assert "приёмник ушёл" in str(record["why"]), "причина не доехала"


def test_the_feed_learns_of_the_retry_only_after_the_retry_has_been_made(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 Сторож ловит ПОРЯДОК, а не наличие строки.

    Запись, положенная в ленту ДО попытки, - это обещание, а не факт, и снять его потом
    было нечем: отказ глотался пустым ``except``. Проверка «строка в ленте есть» такую
    подмену пропускает целиком, поэтому спрашивается ровно одно - ЧТО лента знала о
    повторе в тот миг, когда повтор ещё делался.
    """
    receiver = _Quiet(tape=tape)
    receiver._peak = 1272.4

    assert _reload(receiver) is True

    assert receiver.told == [], "лента пообещала повтор раньше, чем повтор случился"
    assert tape.events() == ["reload"], "а после попытки запись обязана стоять"
    assert "retrying LOAD" in capsys.readouterr().out


def test_two_retries_with_different_fates_leave_traces_that_differ(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 Две ленты одного сценария с РАЗНЫМИ исходами обязаны разойтись между собой.

    Сравниваются они друг с другом, а не с ожиданием: одиночную ленту удовлетворяет любая
    константа, а вот их равенство и есть тот самый дефект. До правки ушедший повтор и
    легший давали в ленте побайтово одну запись, и отличить их можно было только по
    тексту ошибки процесса рядом - то есть НЕ по ленте.
    """
    gone, fell = _traced(breaks=False), _traced(breaks=True)

    assert len(gone) == len(fell) == 1, "оба исхода записаны, молчание тут тоже двусмысленно"
    assert gone != fell, "ушедший повтор и легший стоят в ленте одной строкой"
    assert gone[0]["error"] == fell[0]["error"] == 905, "повод повтора у обоих один и тот же"
    assert capsys.readouterr().out.count("retrying LOAD") == 2, "сценарий у обеих лент один"


def test_stepping_over_a_deadly_segment_moves_the_peak_with_the_show(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """Перешагнули - максимум обязан уехать вместе с показом.

    Иначе следующий нудж прицелится в оставленный позади кусок, а свой же прыжок мы
    примем за перемотку человека.
    """
    receiver = _Quiet()
    receiver.next_cut = lambda at: 137.095 if at < 137.095 else 152.0
    receiver._peak = 127.2
    receiver._deaths[137.095] = receiver.DEADLY_TRIES - 1

    assert _reload(receiver) is True

    (at,) = receiver.loads
    assert at > 127.2, "поднимаемся уже за убивающим куском"
    assert receiver._peak == at
    assert receiver._nudged_to == at
