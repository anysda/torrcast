"""Счёт обхода очереди отбора: чем кончилась каждая осечка и во что она обошлась.

Ведёт его :meth:`torrcast.usecases.select_bench.bench.Bench.resolve`, а читают его
строка отказа (:func:`_bench_refusal`) и запасной ход без русской озвучки.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import _did_not_answer, _silenced, _turned_down


@dataclass(slots=True)
class _Tally:
    """Что обход очереди уже узнал: осечки поимённо, их цена и отложенный безрусский."""

    #: Осечки строками «номер - почему»: из них складывается отказ.
    tried: list[str] = field(default_factory=list)
    #: Приговоры по номерам релизов: нужны строке о снижении ступени (TC-187), чтобы
    #: она называла причину, а не просто «лучшее было».
    judged: dict[int, str] = field(default_factory=dict)
    #: Сколько раздач ffprobe прочитал и осудил.
    verdicts: int = 0
    #: Сколько тронутых раздач промолчали роем (:func:`_silenced`): без этого счёта
    #: приговор осмотра («отдельного видеофайла нет») числился молчанием роя, и отказ
    #: советовал «зайти позже» там, где рой ни при чём - в раздаче просто не картина.
    silents: int = 0
    #: Во что приговоры уже обошлись человеку, секунды (:data:`VERDICT_BUDGET`).
    priced: float = 0.0
    #: Первый годный кандидат, чей паспорт ПРЯМО назвал нерусский язык: он не играет,
    #: пока в очереди есть кого спросить, но и не выбрасывается - это запасной ход на
    #: случай, когда русской не найдётся ни у кого (:meth:`_mute_fallback`).
    mute: _Prep | None = None
    #: Сколько релизов обход забраковал именно звуком: по этому счёту отказ называет
    #: причину своим именем, а не общим «годного релиза нет» (:func:`_bench_refusal`).
    voiceless: int = 0

    def note(
        self, number: int, prep: _Prep, why: str, since: float, clock: Callable[[], float]
    ) -> None:
        """Записать осечку: молчание роя и приговор ffprobe считаются по-разному.

        Молчание роя про КАЧЕСТВО релиза не сказало ничего и попытки не жжёт; приговор
        сказал всё и стоит человеку секунд ожидания (:data:`VERDICT_BUDGET`) - их и
        считают часы, заведённые с ``since``, момента начала ожидания.
        """
        self.tried.append(f"{number} - {why}")
        if _silenced(prep):
            _did_not_answer(number, why)
        else:
            _turned_down(self.judged, number, why)
        self.silents += 1 if _silenced(prep) else 0
        if not prep.error and prep.media is not None:  # ffprobe прочитал и осудил
            self.verdicts += 1
            self.priced += clock() - since

    def hold(self, prep: _Prep, voiceless: bool, forget: Callable[[_Prep], None]) -> None:
        """Отложить кандидата, чей язык звука НАЗВАН; остальных - отпустить.

        Запасной ход держит ОДНОГО отложенного, и держит он только того, про кого паспорт
        сказал прямо: «японский», «английский». Про такую дорожку зрителю есть что сказать
        честной строкой до картинки, и решение остаётся при нём.

        🔴 TC-741. Паспорт, промолчавший про язык, сюда не попадает вовсе. Про его дорожку
        известно ровно одно - что она первая в файле, - и «русской не нашли» отличить от
        «нашли, но не назвали» нечем ни нам, ни зрителю. Прежде такой релиз вытеснял
        названного («незнание лучше знания нет») и играл запасным ходом под строку «звук
        не назван» - то есть отбор возвращался ровно к тем релизам, которые сам же
        забраковал строкой «без русской озвучки». Незнание - это не «сойдёт»: годным
        считается только подтверждённый русский (:func:`voice_unproven`), а неподтверждённый
        и неназываемый - это отказ, а не тихая подмена.

        Между равными выигрывает первый - он выше в ранжире.
        """
        self.voiceless += 1 if voiceless else 0
        if voiceless and prep.found.foreign and self.mute is None:
            self.mute = prep  # запасной ход: русской может не оказаться ни у кого
        else:
            forget(prep)
