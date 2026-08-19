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
    #: Первый годный кандидат, у которого не оказалось русской дорожки: он не играет,
    #: пока в очереди есть кого спросить, но и не выбрасывается - это запасной ход на
    #: случай, когда русской не найдётся ни у кого (:meth:`_mute_fallback`).
    mute: _Prep | None = None

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
        """Отложить безрусского кандидата, если он лучший из них; остальных - отпустить.

        Запасной ход держит ОДНОГО отложенного, и это лучший из безрусских. Лучший
        тут - тот, про кого меньше известно плохого: паспорт, промолчавший про язык,
        ещё может оказаться русским, а названный японским русским уже не станет
        никогда (TC-492). Поэтому незнание вытесняет знание «нет», а между равными
        выигрывает первый - он выше в ранжире.
        """
        better = self.mute is None or (self.mute.found.foreign and not prep.found.foreign)
        if voiceless and better:
            if self.mute is not None:
                forget(self.mute)
            self.mute = prep  # запасной ход: русской может не оказаться ни у кого
        else:
            forget(prep)
