"""Перезабор куска посреди показа обязан быть в ленте - и удавшийся, и легший.

🔴 Сторож стоит против ТИШИНЫ, а не против неверного поля. Перезабор не гасит показ и
снаружи ничем себя не выдаёт: раньше он звался под ``contextlib.suppress``, не писал ни
строки, а отказ глушился ровно теми типами, которыми перезабор и не удаётся. Замер,
считающий заходы по ленте, видел один заход там, где их было четыре, и ни одной неудачи.

Меряется тут РАЗЛИЧИЕ двух лент на одном и том же сценарии, а не наличие строк: тракт,
который снова замолчит, отдаст обе ленты пустыми и одинаковыми, и равенство их - это и
есть покраснение. Проверка «строки есть» такого сторожа не заменяет: её купила бы любая
одна запись без исхода.
"""

from __future__ import annotations

from collections.abc import Callable

from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.mock.hls_decoder import HlsDecoder
from torrcast.adapters.chromecast.mock.screen_watch import ScreenWatch
from torrcast.domain.patience import Patience
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.reception_report import ReceptionReport
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install

WHOLE = 7200.0
STOOD = 300.0
#: Отказ, которым перезабор и не удаётся: тот же ``OSError``, что у живого приёмника.
GONE = OSError("приёмника нет в сети")
#: Столько перезаборов приёмнику отпущено внутри терпения - столько строк и ждём.
RETRIES = 2


def _taken(reopen: Callable[[float], None], retries: int = RETRIES) -> list[dict[str, object]]:
    """Строки ленты за один показ, у которого картинка встала и терпение пошло."""
    tape = Tape()
    install(tape)
    try:
        clock = FakeClock(1000.0)
        report = ReceptionReport(duration=WHOLE)
        decoder = HlsDecoder(report)
        watch = ScreenWatch(decoder, report, CAUTIOUS, Patience(30.0, retries), clock, reopen)
        decoder.pos = Position(STOOD, WHOLE, True)
        watch.read(front=400.0)
        watch.read(front=400.0)  # картинка встала: отсюда и пошло терпение
        for _ in range(retries + 1):
            clock.now += 10.0
            watch.read(front=400.0)
    finally:
        install(Silent())
    return tape.named("refetch")


def _falls(pos: float) -> None:
    """Источника всё ещё нет: перезабор ложится тем же типом, что глушил ``suppress``."""
    raise GONE


def test_a_refetch_that_went_out_and_one_that_fell_do_not_leave_the_same_tape() -> None:
    """🔴 Один и тот же сценарий, разные исходы перезабора - и ленты обязаны разойтись.

    Равенство лент тут и есть авария: молчащий тракт отдаёт обе пустыми, и по такой ленте
    «перезаборов не было» не отличить от «все перезаборы легли».
    """
    went = _taken(lambda pos: None)
    fell = _taken(_falls)

    assert went != fell, f"исход перезабора из ленты не виден: {went} против {fell}"
    assert went and fell, "перезабор не оставил в ленте ни строки - тракт молчит"


def test_every_refetch_leaves_its_own_row_and_not_one_row_for_all_of_them() -> None:
    """Строк ровно столько, сколько перезаборов: по ним замер и считает заходы.

    Одна запись на все попытки прошла бы проверку «лента не пуста» и оставила бы замер
    ровно таким же слепым, каким он был без записей вовсе.
    """
    rows = _taken(_falls)

    assert len(rows) == RETRIES, f"перезаборов было {RETRIES}, а в ленте {len(rows)}: {rows}"
    assert [row["tries"] for row in rows] == [1, 2], "номер попытки обязан расти"
    assert [row["pos"] for row in rows] == [STOOD, STOOD], "место перезабора - где встали"


def test_a_fallen_refetch_is_named_by_the_same_word_the_revival_uses() -> None:
    """🔴 Словарь исходов у сухого тракта один: перезабор говорит «упал», как и подъём.

    Завести перезабору свои слова значило бы развести ленту надвое по-новому: замер читает
    исход одним разбором, и второе слово для той же аварии он просто не найдёт.

    🔴 Непустота ленты проверяется ПЕРВОЙ и отдельно: ``all`` на пустом списке отвечает
    «годен» там, где мерить не на чем, и молчащий тракт купил бы этого сторожа даром.
    """
    fell = _taken(_falls)

    assert len(fell) == RETRIES, f"мерить не на чем: перезаборов в ленте {len(fell)}"
    assert all(row["ok"] is False for row in fell), "легший перезабор не смеет звать себя ушедшим"
    assert all(str(row["why"]).startswith("упал:") for row in fell), f"чужое слово: {fell}"
    assert all("приёмника нет в сети" in str(row["why"]) for row in fell), "причина не доехала"


def test_a_refetch_that_went_out_does_not_claim_the_picture_came_back() -> None:
    """``ok`` - это «перезабор ушёл», а не «картинка вернулась»: врать тут нечем.

    Картинка встала и на этом прогоне не возвращается вовсе, но перезаборы ушли без
    отказа - и лента говорит ровно это, не приписывая показу кадра, которого не было.
    """
    rows = _taken(lambda pos: None)

    assert [row["ok"] for row in rows] == [True, True]
    assert [row["why"] for row in rows] == ["", ""], "исход назван - причине взяться неоткуда"
