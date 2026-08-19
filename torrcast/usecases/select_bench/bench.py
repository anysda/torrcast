"""Стенд параллельной подготовки кандидатов отбора: очередь релизов до годного."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.infra_error import InfraError
from torrcast.domain.pick_settings import MAX_TRIES
from torrcast.domain.server_down_error import ServerDownError
from torrcast.ports.progress.progress import Progress
from torrcast.usecases.rank.heard import heard
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import _waiting_note
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench._bench_prewarm import _BenchPrewarm
from torrcast.usecases.select_bench._bench_queue import _bench_queue
from torrcast.usecases.select_bench._bench_refusal import _bench_refusal
from torrcast.usecases.select_bench._bench_tally import _Tally
from torrcast.usecases.select_bench._retried_verdict import _retried_verdict

if TYPE_CHECKING:
    from torrcast.domain.args import Args


class Bench(_BenchPrewarm):
    """Стенд отбора целиком: обход очереди до годного релиза."""

    def resolve(self, plan: Plan, args: Args, progress: Progress) -> _Prep:
        """Годный релиз плана: ждём подготовку с прогрессом, негодный — следующий.

        Осечки бывают двух разных сортов, и до сих пор они стоили одинаково — попытки из
        трёх:

        * **приговор** — ffprobe раздачу прочитал и она не годится (av1, vc1, тяжёлая),
          либо сам осмотр раздачи ответил за неё («нужной серии нет», «отдельного
          видеофайла нет»). Про релиз узнали всё, второй раз спрашивать нечего;
        * **молчание роя** — метаданные не приехали, поток не прочитался, фаза не
          уложилась в бюджет. Про КАЧЕСТВО релиза при этом не узнали ничего: раздача
          просто не отозвалась.

        Считать их одинаково — это и есть главная причина 🟡 в замере на тысяче запросов:
        три подряд «нет пиров за 20 с» заканчивали отбор словами «годного релиза нет»,
        хотя ниже в очереди стояли живые. Перепроверка тех же картин в один поток
        оживляла шесть из восьми («Кавказская пленница», «Зона интересов», «Бесконечная
        история»).

        Поэтому попытку жжёт только приговор (:data:`MAX_TRIES`), а молчание роя — часы
        (:data:`PICK_BUDGET`). Бесконечно это не длится и молчаливым не бывает: потолок
        фазы прежний, каждая осечка стоит строки, а очередь конечна.

        🔴 TC-436. Потолок фазы держит и ОЖИДАНИЕ внутри попытки (:meth:`_wait`), а не
        только переход к следующей: свежий прогрев, начатый на 179-й секунде, тянул ещё до
        65 с сверх потолка, и объявленные 180 с обходились человеку в 245.

        🔴 TC-300. А кончившаяся очередь, в которой промолчали ВСЕ, кончается не отказом:
        лучший из промолчавших спрашивается ещё раз - один и без отсрочек, в остаток того
        же бюджета фазы (:meth:`_recheck`). Замер: такие отказы не упирались ни в
        приговоры, ни в часы ни разу из 98, то есть терпения им не хватало нашего, а не
        бюджетного.

        🔴 TC-188. Сами приговоры тоже считаются не поштучно, а СЕКУНДАМИ ожидания
        (:data:`VERDICT_BUDGET`): три места счётчика сгорали на именах, которые ffprobe
        читает за секунду, - SD-рип на 1.5 ГБ, vp9, av1, - и до живого 1080p ниже по
        очереди дело не доходило (44 случая в замере каталога). Дешёвый приговор больше
        не отнимает место у следующей раздачи, дорогой отнимает как отнимал.

        🔴 TC-178, TC-492. Третья осечка - **звук**: «включилось» значит «включилось С
        РУССКОЙ ОЗВУЧКОЙ», и годен только ПОДТВЕРЖДЁННЫЙ русский (:func:`voice_unproven`).
        Считается она как приговор - про релиз узнали всё, - и упирается в те же два
        потолка. Лишнего времени это не стоит: спрашивается уже прочитанный паспорт. И
        гейт не слепой: первый безрусский, но во всём остальном годный кандидат ждёт в
        стороне и играет, если русской не найдётся ни у кого (:meth:`_mute_fallback`).
        """
        queue = _bench_queue(plan, args)
        # Верх и запасной готовятся независимо: паспорт второго релиза не ждёт первого.
        # Третий до счастливого пути не относится и стартует в цикле ниже, только если
        # первые два действительно не подошли. Иначе быстрый русский верх оплачивал бы
        # третий ffprobe лишь из-за того, как планировщик разложил три фоновых потока.
        for number in queue[:2]:
            self.start(plan, number)
        #: Осечки, их цена и отложенный безрусский - всё, что обход уже узнал.
        tally = _Tally()
        exhausted = False
        #: Докуда дошла очередь - для строки о снижении ступени на запасном ходу.
        reached = 0
        deadline = self.clock() + self.pick_budget
        for attempt, number in enumerate(queue, start=1):
            reached = attempt
            following = queue[attempt] if attempt < len(queue) else None
            # Нужны ровно двое: тот, чьего ответа ждём, и тот, кто греется ему на смену.
            # Всё прочее прогретое потолок вправе убрать прямо здесь (:meth:`_room`).
            # Третий - отложенный безрусский: его раздача ещё может понадобиться показу.
            keep = (number, following, tally.mute.number if tally.mute is not None else None)
            self.needed = {(plan.picture.key, n) for n in keep if n is not None}
            prep = self.start(plan, number)
            self._ask(plan, prep, queue)
            if following is not None:  # запасной греется, пока ждём этот
                self.start(plan, following)
            # Секундомер стоит вокруг ОЖИДАНИЯ, а не вокруг работы потока: прогретая под
            # меню раздача отвечает мгновенно, и её приговор человеку ничего не стоил.
            entered = self.clock()
            voice_search = (
                "" if args.pinned else f"ищу русскую озвучку: релиз {attempt} из {len(queue)} - "
            )
            self._wait(prep, progress, prefix=voice_search, limit=deadline)
            # Ошибка самой службы раздачи относится ко всей очереди, а не к одному
            # рою. Перебирать остальные релизы бессмысленно: они пойдут через тот же
            # мёртвый порт и лишь размножат одну строку, после чего итог ещё и свалит
            # вину на раздачи. Опознаётся такой отказ ТИПОМ исключения, а не текстом:
            # строка печатается языком зрителя и правится, тип - нет (TC-281).
            if isinstance(prep.failure, ServerDownError):
                raise InfraError(prep.error)
            trouble = self._trouble(
                prep,
                pinned=args.pinned,
                warn_mbit=plan.warn_mbit,
                recode=plan.recode_at > 0,
                hard_mbit=plan.hard_mbit,
            )
            # 🔴 TC-178. Русская дорожка - часть «включилось», а не предпочтение: релиз,
            # у которого её нет, годным не считается, и очередь идёт дальше. Спрашивается
            # уже прочитанный паспорт (:func:`voice_unproven`) - ни одного лишнего ffprobe
            # и ни одного лишнего похода в рой это не стоит. Названный руками релиз не
            # судим: там человек выбрал сам.
            #
            # 🔴 TC-492. Годен только ПОДТВЕРЖДЁННЫЙ русский звук. Дорожка без тега языка
            # раньше проходила гейт наравне с русской, и это была не поблажка, а подмена
            # правила незнанием: очередь вставала на первом же безымянном релизе.
            voiceless = (
                not trouble
                and not args.pinned
                and voice_unproven(prep.found, native=plan.picture.native)
            )
            if not trouble and not voiceless:
                progress.phase("")
                prep = self._honest(plan, prep, queue, args, progress, tally.judged)
                self._announce(plan, prep, queue, tally.judged, attempt)
                return prep
            why = _waiting_note(prep, trouble) if trouble else "без русской озвучки"
            tally.note(number, prep, why, entered, self.clock)
            tally.hold(prep, voiceless, self._forget)
            progress.phase("")
            # Три приговора - пол, дальше решают секунды: дешёвые приговоры (SD-рип,
            # vp9) места следующей раздаче больше не занимают, дорогие занимают.
            affordable = tally.verdicts < MAX_TRIES or tally.priced < self.verdict_budget
            goes_on = following is not None and affordable and self.clock() < deadline
            tail = f" - беру {following}" if goes_on else ""
            head = (
                f"релиз {number} без русской озвучки ({heard(prep.found)})"
                if voiceless
                else f"релиз {number} не годится ({why})"
            )
            print(head + tail)
            if not goes_on:
                # Дошли до конца очереди, а не встали по бюджету/попыткам: следующего нет.
                exhausted = following is None
                break
        if tally.mute is not None:
            return self._mute_fallback(
                plan, tally.mute, queue, tally.judged, reached, len(tally.tried)
            )
        if tally.verdicts == 0 and exhausted and tally.tried:
            judged_before = set(tally.judged)
            revived = self._recheck(plan, queue, args, progress, tally.judged, deadline)
            if revived is not None:
                return revived
            tally.tried, tally.silents = _retried_verdict(
                queue, tally.judged, judged_before, tally.tried, tally.silents
            )
        _bench_refusal(plan, queue, tally.tried, tally.silents, exhausted, args.release)
