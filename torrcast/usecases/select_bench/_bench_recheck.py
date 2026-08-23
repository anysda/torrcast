"""Второй спрос очереди, промолчавшей целиком: одному релизу и без отсрочек."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.infra_error import InfraError
from torrcast.domain.server_down_error import ServerDownError
from torrcast.ports.progress.progress import Progress
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import _did_not_answer, _silenced, _turned_down
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench._bench_notes import _BenchNotes

if TYPE_CHECKING:
    from torrcast.domain.args import Args


class _BenchRecheck(_BenchNotes):
    """Второй спрос промолчавшей очереди."""

    def _recheck(
        self,
        plan: Plan,
        queue: list[int],
        args: Args,
        progress: Progress,
        judged: dict[int, str],
        deadline: float,
    ) -> _Prep | None:
        """Второй спрос очереди, промолчавшей целиком: одному релизу и без отсрочек.

        🔴 TC-300. Отказ «до остальных отбор не дошёл» звучал так, будто обход упёрся в
        потолок, и потолки же в нём и подозревали. Замер по двум сохранённым прогонам
        (1131 запрос, 98 таких отказов) говорит обратное: НИ ОДИН из них не встал ни по
        приговорам (:data:`MAX_TRIES` - их там ноль по определению ветки), ни по часам
        (самый долгий занял 91 с из 180 :data:`PICK_BUDGET`). Очередь всякий раз доходила
        до собственного конца, и кончалась она тем, что каждый её релиз промолчал роем; в
        56 отказах из 98 при этом потрогали ВСЮ выдачу до последней раздачи. Поднимать
        потолки тут нечего - поднимать надо терпение.

        Молчание это часто ложное. Тот же корпус запросов, прогнанный дважды тем же кодом
        в один день: из 17 картин, отказанных молчанием роя в первом прогоне, во втором
        сыграли 8, и наоборот - из 13 отказанных во втором в первом сыграли 5. Живой рой,
        которого не дождались, выглядит точно так же, как мёртвый.

        Не дождались его МЫ, и ровно на столько, на сколько сами назначили: отсрочки
        (:data:`PEER_GRACE`, :data:`SWARM_GRACE`) обрывают раздачу втрое-вчетверо раньше
        её собственного бюджета. Заведены они по честному расчёту - «ошибка стоит одного
        места в очереди, следующий релиз всё равно спрашивается», - и расчёт этот верен
        ровно до тех пор, пока в очереди есть кого спрашивать. Когда промолчали все,
        ошибка отсрочки стоит уже не места, а всего показа, а бюджет фазы при этом не
        потрачен и наполовину (медиана такого отказа - 23 с из 180).

        Поэтому перед отказом лучший из промолчавших спрашивается ещё раз: один (соседей
        рядом не греется), по полным бюджетам метаданных и дорожек, без единой отсрочки.
        Потолок фазы стоит где стоял - второго спроса не будет вовсе, если остаток бюджета
        не покрывает его худшую цену, - и стоит он строки в обе стороны: и когда идёт, и
        когда рой промолчал повторно.

        Спрашивается тот, про кого мы правда ничего не знаем (:func:`_silenced`): раздачу
        без нужной серии терпение не изменит.
        """
        key = plan.picture.key
        number = next((n for n in queue if _silenced(self.preps.get((key, n)))), None)
        if number is None:  # молчал не рой, а сами раздачи - им терпение не поможет
            return None
        # Спрашивается по ПОЛНОМУ сроку одной раздачи (:meth:`_wait`), поэтому и место под
        # него считается по полному: те же +5 с, иначе второй спрос уносил обход за потолок
        # фазы на пять секунд - тот же промах, что и в :meth:`resolve` (TC-436).
        if self.clock() + self.meta_budget + self.probe_budget + 5.0 > deadline:
            return None  # честный второй спрос в остаток бюджета фазы уже не влезает
        print(
            f"промолчала вся очередь ({len(queue)}) - спрашиваю релиз {number} "
            f"ещё раз, одного и без отсрочек (жду до {self.meta_budget + self.probe_budget:g} с)"
        )
        # Прогрев, оборванный отсрочкой, уже забыт вместе с раздачей: спрашиваем заново.
        self.preps.pop((key, number), None)
        self.needed = {(key, number)}
        prep = self.start(plan, number, patient=True)
        self._wait(
            prep,
            progress,
            prefix=f"ищу русскую озвучку: релиз {queue.index(number) + 1} из {len(queue)} - ",
        )
        progress.phase("")
        if isinstance(prep.failure, ServerDownError):
            raise InfraError(prep.error)
        trouble = self._trouble(
            prep,
            pinned=args.pinned,
            warn_mbit=plan.warn_mbit,
            recode=plan.recode_at > 0,
            hard_mbit=plan.hard_mbit,
        )
        if trouble:
            silent = _silenced(prep)
            if silent:
                _did_not_answer(number, trouble)
            else:
                _turned_down(judged, number, trouble)
            result = "молчит и в одиночку" if silent else "ответил в одиночку, но не годится"
            print(f"релиз {number} {result} ({trouble})")
            self._forget(prep)
            return None
        if not args.pinned and voice_unproven(prep.found, native=plan.picture.native):
            # Ожил безрусский: русской не нашлось ни у кого, кого вообще удалось спросить.
            # 🔴 TC-741. Играет он только если язык НАЗВАН: тогда зритель слышит, чей это
            # звук, и решает сам. Паспорт, промолчавший про язык, тут ровно тот же отказ,
            # что и в обходе очереди, - подставлять первую дорожку файла молча нельзя.
            if prep.found.foreign:
                return self._mute_fallback(plan, prep, queue, judged, len(queue), len(queue))
            _turned_down(judged, number, "без русской озвучки")
            print(f"релиз {number} ответил в одиночку, но без русской озвучки")
            self._forget(prep)
            return None
        # Проверки честности (:meth:`_honest`) тут нет по той же причине, что и на запасном
        # ходу: сравнивать не с кем - все соседи уже ответили молчанием, и второй круг
        # ffprobe спрашивал бы ровно тех, кто только что промолчал.
        self._announce(plan, prep, queue, judged, len(queue))
        return prep
