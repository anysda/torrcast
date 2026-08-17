"""Стенд параллельной подготовки кандидатов отбора."""
# ruff: noqa
# mypy: ignore-errors

from __future__ import annotations

from torrcast.ports.journal import journal

from torrcast.domain.torrcast_error import TorrcastError

from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, COPY

from torrcast.domain.pick_settings import (
    HONEST_BUDGET,
    MAX_TRIES,
    META_BUDGET,
    PICK_BUDGET,
    PROBE_BUDGET,
    VERDICT_BUDGET,
)

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import Profile, REFUSE
from torrcast.domain.recode_note import recode_note
from torrcast.domain.recode_settings import RECODE_HEIGHT
from torrcast.domain.release import Release
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.torr_file import TorrFile

__all__: list[str] = []

import threading
import time
from collections.abc import Callable

from torrcast.ports.legacy_namespace import legacy_namespace

globals().update(
    legacy_namespace(
        torrcast__console=("Progress",),
        torrcast__stream=(
            "ContactWait",
            "TorrServer",
            "probe",
            "swarm_pulse",
            "warm_file",
        ),
    )
)


class _Bench:
    """Прогрев релизов: несколько раздач готовятся разом, показ берёт первую годную.

    Держит по потоку на релиз и умеет ждать нужный с живым прогрессом. Любая осечка
    (нет пиров, не читается поток, оказался HEVC) стоит одной строки и перехода к
    следующему кандидату — молчаливых подмен и молчаливых зависаний не бывает.
    """

    def __init__(
        self,
        torrserver: TorrServer,
        choose: Callable[[_Plan, Release, list[TorrFile]], TorrFile] | None = None,
        meta_budget: float = META_BUDGET,
        probe_budget: float = PROBE_BUDGET,
        profile: Profile = CAUTIOUS,
        prober: Callable[..., Media] | None = None,
        pick_budget: float | None = None,
        verdict_budget: float | None = None,
        honest_budget: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.torrserver = torrserver
        self.choose = choose or _default_file
        #: Чем читаются дорожки раздачи: подделке отбора хватает и её собственного ответа.
        self.prober = prober or probe
        #: Чей декодер судит релизы: что играется копией, а что не играется вовсе.
        self.profile = profile
        self.meta_budget = meta_budget
        self.probe_budget = probe_budget
        #: Потолки фазы отбора: обход очереди, приговоры и ожидание честного запасного.
        self.pick_budget = PICK_BUDGET if pick_budget is None else pick_budget
        self.verdict_budget = VERDICT_BUDGET if verdict_budget is None else verdict_budget
        self.honest_budget = HONEST_BUDGET if honest_budget is None else honest_budget
        #: Часы отбора: все его сроки меряются отсюда, а не стенными часами напрямую.
        self.clock = clock
        self.preps: dict[tuple[str, int], _Prep] = {}
        #: Прогревы, которые прямо сейчас кому-то нужны и потолком не убираются: тот, чьего
        #: ответа ждут, и тот, который греется ему на смену. Пусто под меню - там нужны все.
        self.needed: set[tuple[str, int]] = set()

    def start(self, plan: _Plan, number: int, patient: bool = False) -> _Prep:
        """Начать (или вернуть уже начатую) подготовку релиза ``number`` этого плана.

        ``patient`` - спрашивать рой без отсрочек, по полным бюджетам фазы
        (:attr:`_Prep.patient`). Обычный прогрев начинает работу сразу, но часы
        отсрочки запускаются только когда релиз действительно дошёл до вопроса.
        """
        key = (plan.picture.key, number)
        found = self.preps.get(key)
        if found is not None:
            return found
        self._room()
        prep = _Prep(
            number=number,
            release=plan.ranked[number - 1],
            patient=patient,
            contact_wait=None if patient else ContactWait(PEER_GRACE),
        )
        self.preps[key] = prep
        threading.Thread(target=self._work, args=(plan, prep), daemon=True).start()
        return prep

    @staticmethod
    def _ask(plan: _Plan, prep: _Prep, queue: list[int]) -> None:
        """Запустить часы первого контакта, когда релиз дошёл до вопроса."""
        if prep.contact_wait is not None:
            prep.contact_wait.activate(peer_grace(plan, prep.number, queue))

    def live(self) -> list[_Prep]:
        """Прогревы, за которыми в TorrServer стоит (или вот-вот встанет) наша раздача."""
        return [prep for prep in self.preps.values() if not prep.dropped]

    def _room(self) -> None:
        """Освободить место под новую раздачу: одновременно держим не больше :data:`MAX_LIVE`.

        Убирается САМЫЙ СТАРЫЙ из ненужных - тот, чей прогрев начался раньше всех и кого
        никто не ждёт (:attr:`needed`). Порядок именно такой, а не «последний заведённый»:
        свежий прогрев - это работа, которая ещё идёт и вот-вот пригодится, а старый под
        меню уже отдал всё, что мог.

        🔴 Убирается по ЯВНОМУ ХЭШУ прогрева (:meth:`_forget`), а не «всё, что видно в
        списке службы»: в списке лежат и ЧУЖИЕ раздачи, а «снести всё из list» уже сносило
        их. Своё в списке как раз видно - проверено на TorrServer MatriX.142.2, наша
        раздача держится в ``action:list`` весь показ и пропадает лишь после перезапуска
        службы (``save_to_db:false``). Список не врёт, он просто не наш.
        """
        while len(self.live()) >= MAX_LIVE:
            spare = [
                prep
                for key, prep in self.preps.items()
                if not prep.dropped and key not in self.needed
            ]
            if not spare:  # все живые нужны - потолок не повод убивать работу под ответом
                return
            self._forget(min(spare, key=lambda prep: prep.started))

    def reorder(self, before: _Plan, after: _Plan) -> _Plan:
        """Переставить уже начатые прогревы под НОВЫЙ порядок отбора; вернуть новый план.

        Прогрев под меню заводится по номеру релиза в плане (:meth:`start`), а номер —
        это место в :attr:`_Plan.ranked`. Пересборка плана на настоящей длительности
        (:func:`_timed`) порядок вправе поменять, и без переезда ключей прогрев верха
        отдался бы уже другой раздаче: та же цифра, другой магнит.

        Переезд считается по самой раздаче, а не по цифре: у прогрева она уже лежит
        (:attr:`_Prep.release`), и ищется её новое место. Раздачи, которой в новом
        порядке нет вовсе, быть не может — пул тот же, — но если она пропадёт, прогрев
        отпускается, а не переносится наугад.
        """
        if after is before:
            return before
        places = {id(release): number for number, release in enumerate(after.ranked, start=1)}
        moved: dict[tuple[str, int], _Prep] = {}
        for key, prep in self.preps.items():
            if key[0] != after.picture.key:
                moved[key] = prep
                continue
            number = places.get(id(prep.release))
            if number is None:  # раздача выпала из порядка - её прогрев больше не нужен
                self._forget(prep)
                continue
            prep.number = number
            moved[(key[0], number)] = prep
        self.preps = moved
        self.needed = {
            (key, places.get(id(before.ranked[number - 1]), number))
            if key == after.picture.key and 1 <= number <= len(before.ranked)
            else (key, number)
            for key, number in self.needed
        }
        return after

    def keep_plan(self, plan: _Plan) -> None:
        """Картина выбрана - прогревы ОСТАЛЬНЫХ картин больше не нужны, и они убираются.

        До сих пор они доживали до :meth:`keep_only`, то есть до конца отбора, - а отбор
        это до :data:`PICK_BUDGET` секунд (180). Всё это время две-три чужие раздачи
        тянули куски у той единственной, которую мы вот-вот покажем, и подставляли
        TorrServer под его же таймер (:data:`MAX_LIVE`).

        Внутри выбранной картины не трогается ничего: запасной релиз греется параллельно
        верху НАМЕРЕННО (:meth:`spare`, замеренный выигрыш - 5 с), и убрать его вправе
        только сам отбор, когда выбор уже сделан.
        """
        for key, prep in self.preps.items():
            if key[0] != plan.picture.key:
                self._forget(prep)

    def spare(self, plan: _Plan, args: Args) -> list[_Prep]:
        """Поднять запасной релиз этого плана - тот, к которому уйдёт отбор, если верх забракуют.

        Отличие от :meth:`start` только во времени. Очередь релизов та же самая, что
        спросит :meth:`resolve` (:meth:`_Plan.candidates`), и следующий номер в ней -
        ровно тот, который resolve поднимает первым же движением. Здесь он поднимается
        раньше: пока на экране висит меню, а не после того, как верх уже осуждён.

        Логику ОТБОРА это не трогает ни на знак: кто годен, решает по-прежнему
        :meth:`_trouble`, порядок очереди прежний, и печатается всё то же самое. Меняется
        только то, какая раздача к моменту отбора уже прогрета.

        Названный руками релиз (``--release N``) запасного не имеет по определению: очередь
        из одного номера, подменять человека нечем - и лишней раздачи в TorrServer не будет.

        🔴 TC-309. Второй запасной - по ЗВУКУ. Релиз, чьё имя русской дорожки не обещает,
        может оказаться «дорожкой без тега», а гейт такой релиз бракует и уводит очередь
        дальше (:func:`voice_unproven`, TC-492) - к той самой раздаче, которая русскую
        обещает. Стоит она в очереди где угодно - на 4-9 месте, - и подъём её с нуля это
        метаданные роя 3-6 с плюс чтение дорожек, то есть половина всего срока отбора.
        Здесь она греется заодно с обычным запасным, и очереди достаётся уже готовый ответ.

        Греется ровно тогда, когда очередь и правда может уйти дальше верха. Спрашивается
        не верх, а тот, кого отбор реально возьмёт, поэтому молчаливое имя ищется среди
        первых :data:`MAX_TRIES` кандидатов - верх и два ближайших запасных; а картина, у
        которой русскую обещали все трое, лишней раздачи в рое не получает вовсе.
        """
        if args.release is not None:
            return []
        queue = plan.candidates(args)
        preps = [self.start(plan, number) for number in queue[1 : 1 + PREWARM_SPARE]]
        front = queue[:MAX_TRIES]
        if any(not plan.ranked[n - 1].dubbed for n in front):
            dub = next((n for n in queue[1:] if plan.ranked[n - 1].dubbed), None)
            if dub is not None:  # совпал с обычным запасным - тот уже греется (:meth:`start`)
                preps.append(self.start(plan, dub))
        return preps

    def resolve(self, plan: _Plan, args: Args, progress: Progress) -> _Prep:
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

        🔴 TC-178. Третья осечка - **звук**: «включилось» значит «включилось С РУССКОЙ
        ОЗВУЧКОЙ», и релиз, у которого русской дорожки не оказалось, годным не считается.
        Судит паспорт, а не имя (:func:`voice_unproven`): имя врёт и молчит, а до ffprobe
        язык звука не знает никто. Считается такая осечка как приговор - про релиз узнали
        всё, - и поэтому упирается в те же :data:`MAX_TRIES` и :data:`VERDICT_BUDGET`, что
        и остальные: гейт не имеет права стать бесконечным перебором выдачи, цель пути
        прежняя - десять секунд до картинки.

        🔴 TC-492. Годен только ПОДТВЕРЖДЁННЫЙ русский звук, и это не придирка к формулировке.
        Паспорт отвечает тремя ответами, а гейт до сих пор пропускал два: и «русская есть»,
        и «язык не назван». Второй ответ - незнание, а не согласие, и по замеру паспортов
        он приходит у 11% сыгранных релизов: ровно на них очередь и вставала, не дойдя до
        нетронутых соседей. Ни одного лишнего ffprobe правка не стоит - меняется только то,
        как читается уже прочитанный ответ, - а перебор остаётся под теми же двумя
        потолками.

        Лишнего времени гейт не стоит вовсе: спрашивается уже прочитанный паспорт, второго
        ffprobe и второго похода в рой на релиз не появляется. Дороже становится ровно
        один случай - когда верх отбора оказался без подтверждённой русской, и это ровно
        тот случай, ради которого всё и затевалось.

        И гейт не слепой: первый безрусский, но во всём остальном годный кандидат
        откладывается в сторону, а не выбрасывается, и если русской не найдётся ни у кого,
        играет он (:meth:`_mute_fallback`). Человек без картины не остаётся.
        """
        queue = plan.candidates(args)
        # Пул, очередь и весь отсев с причинами - одним событием на запрос (TC-186).
        # Сумма очереди и причин сходится с пулом картины: раздача, не доехавшая до
        # каста, больше не исчезает молча (:func:`queue_drops`).
        drops = queue_drops(plan, queue, pinned=args.release is not None)
        journal().emit(
            "select",
            "queue",
            pool=len(plan.picture.releases),
            queued=len(queue),
            dropped=drops,
        )
        if not queue:
            # 🔴 TC-432. Ворота не пропустил НИКТО, включая верх ранжира. Подставить
            # отсеянное значило бы сыграть игру или репак на запрос сериала - подмена
            # картины, худший вид брака. Отказ честный: сколько раздач было, почему
            # каждая не годится и какой у человека ход - всё это :func:`unfit_line`.
            raise NotFoundError(unfit_line(plan, drops, plan.kin))
        if args.release is None and (skipped := plan.skipped):
            # Молчать тут нельзя: человек попросил серию, а половину выдачи мы не взяли.
            print(
                f"серии {plan.want} нет в раздачах: {len(skipped)} "
                f"(«{_cut(skipped[0].raw_name, 60)}»...) - беру ту, где она есть"
            )
        # Верх и запасной готовятся независимо: паспорт второго релиза не ждёт первого.
        # Третий до счастливого пути не относится и стартует в цикле ниже, только если
        # первые два действительно не подошли. Иначе быстрый русский верх оплачивал бы
        # третий ffprobe лишь из-за того, как планировщик разложил три фоновых потока.
        for number in queue[:2]:
            self.start(plan, number)
        tried: list[str] = []
        #: Приговоры по номерам релизов: нужны строке о снижении ступени (TC-187), чтобы
        #: она называла причину, а не просто «лучшее было».
        judged: dict[int, str] = {}
        verdicts = 0
        #: Сколько тронутых раздач промолчали роем (:func:`_silenced`): без этого счёта
        #: приговор осмотра («отдельного видеофайла нет») числился молчанием роя, и отказ
        #: советовал «зайти позже» там, где рой ни при чём - в раздаче просто не картина.
        silents = 0
        #: Во что приговоры уже обошлись человеку, секунды (:data:`VERDICT_BUDGET`).
        priced = 0.0
        exhausted = False
        #: Первый годный кандидат, у которого не оказалось русской дорожки: он не играет,
        #: пока в очереди есть кого спросить, но и не выбрасывается - это запасной ход на
        #: случай, когда русской не найдётся ни у кого (:meth:`_mute_fallback`).
        mute: _Prep | None = None
        #: Докуда дошла очередь - для строки о снижении ступени на запасном ходу.
        reached = 0
        deadline = self.clock() + self.pick_budget
        for attempt, number in enumerate(queue, start=1):
            reached = attempt
            following = queue[attempt] if attempt < len(queue) else None
            # Нужны ровно двое: тот, чьего ответа ждём, и тот, кто греется ему на смену.
            # Всё прочее прогретое потолок вправе убрать прямо здесь (:meth:`_room`).
            # Третий - отложенный безрусский: его раздача ещё может понадобиться показу.
            keep = (number, following, mute.number if mute is not None else None)
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
                prep = self._honest(plan, prep, queue, args, progress, judged)
                self._announce(plan, prep, queue, judged, attempt)
                return prep
            why = _waiting_note(prep, trouble) if trouble else "без русской озвучки"
            tried.append(f"{number} - {why}")
            if _silenced(prep):
                _did_not_answer(number, why)
            else:
                _turned_down(judged, number, why)
            silents += 1 if _silenced(prep) else 0
            if not prep.error and prep.media is not None:  # ffprobe прочитал и осудил
                verdicts += 1
                priced += self.clock() - entered
            # Запасной ход держит ОДНОГО отложенного, и это лучший из безрусских. Лучший
            # тут - тот, про кого меньше известно плохого: паспорт, промолчавший про язык,
            # ещё может оказаться русским, а названный японским русским уже не станет
            # никогда (TC-492). Поэтому незнание вытесняет знание «нет», а между равными
            # выигрывает первый - он выше в ранжире.
            if voiceless and (mute is None or (mute.found.foreign and not prep.found.foreign)):
                if mute is not None:
                    self._forget(mute)
                mute = prep  # запасной ход: русской может не оказаться ни у кого
            else:
                self._forget(prep)
            progress.phase("")
            # Три приговора - пол, дальше решают секунды: дешёвые приговоры (SD-рип,
            # vp9) места следующей раздаче больше не занимают, дорогие занимают.
            affordable = verdicts < MAX_TRIES or priced < self.verdict_budget
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
        if mute is not None:
            return self._mute_fallback(plan, mute, queue, judged, reached, len(tried))
        if verdicts == 0 and exhausted and tried:
            judged_before_recheck = set(judged)
            revived = self._recheck(plan, queue, args, progress, judged, deadline)
            if revived is not None:
                return revived
            # Повторный полный спрос может не промолчать, а вынести приговор: например,
            # метаданные приехали, но нужной серии в раздаче нет. Тогда итог обязан
            # говорить о приговоре, а не обещать, что молчавший рой позже оживёт.
            retried = next(
                (
                    number
                    for number in queue
                    if number in judged and number not in judged_before_recheck
                ),
                None,
            )
            if retried is not None:
                tried = [
                    f"{retried} - {judged[retried]}" if row.startswith(f"{retried} - ") else row
                    for row in tried
                ]
                silents -= 1
        shown = "; ".join(tried[:MAX_TRIES])
        more = f" и ещё {len(tried) - MAX_TRIES}" if len(tried) > MAX_TRIES else ""
        offer = kin_line(plan.kin)
        tail = f"\n{offer}" if offer else ""
        if silents == len(tried) and tried:
            # «Не нашли» и «рой промолчал» - разные отказы. Ни один тронутый релиз не
            # дошёл до приговора: ffprobe не прочитал ни одного, потому что не приехали
            # ни метаданные по DHT, ни поток. Раздачи есть и по именам годны - молчит
            # рой, а не выбор. Врать «годного релиза нет» тут нельзя. Но и «рой мёртв»
            # на всю выдачу - враньё ровно так же: очередь отбора это НЕ вся выдача, и
            # сколько из неё потрогали, знают только счётчики - они и печатаются
            # (:func:`silent_swarm`).
            # 🔴 TC-435. Исчерпания очереди ветка больше не ждёт. Обход 60 молчащих
            # роёв «Дюны», вставший по часам (:data:`PICK_BUDGET`), кончался словами
            # «годного релиза нет» - а негодных не нашли ни одного: их не прочитали.
            # Молчание роя названо молчанием роя независимо от того, кончилась очередь
            # или кончилось время; какое из двух - :func:`silent_swarm` знает по своим
            # счётчикам и говорит числом.
            # 🔴 TC-399. Ветка - только когда промолчали ВСЕ тронутые. Приговор осмотра
            # («отдельного видеофайла нет», «нужной серии нет») молчанием роя не является:
            # про такую раздачу известно всё, и «зайди позже - рой оживёт» было бы ложью.
            raise NotFoundError(
                silent_swarm(plan, queue, len(tried), f"{shown}{more}", picked=args.release) + tail
            )
        refused = f"годного релиза нет ({shown}{more})"
        if exhausted and len(set(queue)) == len(plan.ranked):
            if offer:
                raise NotFoundError(refused + tail)
            raise NotFoundError(
                refused + ": назови картину иначе - другой запрос соберёт другую выдачу"
            )
        move = "выбери другой релиз" if args.release is not None else "выбери руками"
        raise NotFoundError(
            f"{refused}: {move} - cast releases <запрос>, потом cast <запрос> --release N" + tail
        )

    def _recheck(
        self,
        plan: _Plan,
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
            return self._mute_fallback(plan, prep, queue, judged, len(queue), len(queue))
        # Проверки честности (:meth:`_honest`) тут нет по той же причине, что и на запасном
        # ходу: сравнивать не с кем - все соседи уже ответили молчанием, и второй круг
        # ffprobe спрашивал бы ровно тех, кто только что промолчал.
        self._announce(plan, prep, queue, judged, len(queue))
        return prep

    def _announce(
        self,
        plan: _Plan,
        prep: _Prep,
        queue: list[int],
        judged: dict[int, str],
        reached: int,
    ) -> None:
        """Строки перед стартом: чем играем и чего это стоило. Молчаливых подмен нет.

        Собраны в одном месте, потому что путей к показу теперь два - обычный и запасной
        ход без русской озвучки (:meth:`_mute_fallback`), - а строки на них обязаны быть
        одни и те же: и «перекодирую целиком», и «ступень ниже доступной» относятся к
        файлу, а не к тому, как отбор до него добрался.
        """
        # Молчаливых подмен нет ни в одну сторону: и «ресивер может не взять», и
        # «перекодирую целиком» - это решение показа, и человек его слышит. Вес
        # тут такой же повод, как кодек: тяжёлый ремукс уезжает перекодированным
        # целиком, и сказано об этом ровно теми же словами и тем же числом.
        weight = prep.found.weight_mbit(prep.want.size)
        heavy = plan.hard_mbit > 0 and weight > plan.hard_mbit
        if hope := last_hope_note(plan, prep.release):
            print(hope)
        if plan.recode_at > 0 and (prep.found.recoded_whole or heavy):
            # Причина - кодек (с глубиной, если она и есть причина) либо вес.
            silent = prep.found.recoded_whole
            print(recode_note(prep.found.video_name, 0.0 if silent else weight))
        elif warning := prep.found.video_warning:
            print(warning)
        # Ступень ниже доступной - тоже авто-решение, и оно не молчит (TC-187).
        if step := stepdown_note(plan, prep.number, prep.media, queue, judged, reached):
            print(step)

    def _mute_fallback(
        self,
        plan: _Plan,
        mute: _Prep,
        queue: list[int],
        judged: dict[int, str],
        reached: int,
        tried: int,
    ) -> _Prep:
        """Запасной ход: русской дорожки не нашлось ни у кого - играем то, что есть.

        🔴 TC-178. Гейт русской озвучки нельзя делать слепым. Русская дорожка - условие
        годности релиза, но у картины её может не быть НИ У КОГО: японский тайтл, который
        никто не озвучивал, старое кино, чужой сериал. Отказать в такой картине значило бы
        отобрать у человека и то, что есть, - а он про неё ничего плохого не спрашивал.

        Поэтому ступеней две. Пока в очереди есть кого спросить, безрусский релиз ждёт в
        стороне (его раздача при этом не убирается - иначе запасной ход стоил бы второго
        подъёма с нуля). Кончилась очередь - он играет, и решение это громкое: строка на
        экране, запись в недельном следе (по ней замер и считает дыры каталога) и честная
        строка про язык звука перед стартом (:func:`sound_note`).

        🔴 TC-492. Сюда же приходит и третий ответ паспорта - «язык не назван»
        (:func:`voice_unproven`). Раньше такой релиз играл молча, как будто русская в нём
        нашлась; теперь он идёт тем же ходом и той же строкой, а язык в ней называется
        честно - «не назван» (:func:`heard`), а не выдуманным «оригинальным». Отдельной
        строки под этот случай не заводится намеренно: зрителю важно одно - русскую
        озвучку не нашли, - а чем именно кончился паспорт, ему договаривает
        :func:`sound_note` перед стартом.

        Проверки честности (:meth:`_honest`) тут нет намеренно: она меняет релиз ради
        разрешения, а на этом пути мы уже знаем, что русской дорожки нет ни у одного из
        проверенных, и второй круг ffprobe стоил бы секунд ровно за то же самое.
        """
        lang = heard(mute.found)
        journal().emit("select", "mute", release=mute.number, lang=lang, checked=tried)
        unnamed_promise = default_unnamed(mute.found) and mute.release.dubbed
        if unnamed_promise:
            print(
                f"русская озвучка не подтверждена ни в одной из проверенных раздач "
                f"({tried}) - включаю релиз {mute.number}: звук без метки языка, "
                "имя релиза обещает русский"
            )
        else:
            print(
                f"русской озвучки нет ни в одной из проверенных раздач ({tried}) - "
                f"включаю релиз {mute.number}, звук {lang}"
            )
        self._announce(plan, mute, queue, judged, reached)
        return mute

    def _wait(self, prep: _Prep, progress: Progress, prefix: str = "", limit: float = 0.0) -> None:
        """Дождаться подготовки, показывая фазу и бегущее время.

        ``limit`` - потолок ФАЗЫ отбора (:data:`PICK_BUDGET`), а срок выше - потолок одной
        раздачи. Ждём до ближайшего из двух.

        🔴 TC-436. Без ``limit`` потолок фазы проверялся только МЕЖДУ попытками
        (:meth:`resolve`), а ожидание внутри попытки шло по своему сроку до конца: свежий
        прогрев, начатый на 179-й секунде, тянул ещё до 65 с (метаданные плюс проба плюс
        5), и худший обход стоил человеку около 245 с вместо объявленных 180.

        Срезается ровно ожидание сверх потолка, и ни секундой раньше: раздача, прогретая
        под меню (:data:`PREWARM_SPARE`), отвечает мгновенно, и спросить её мы обязаны
        хоть на 179-й секунде - потолки роя тут не режутся, режется выход за потолок фазы.
        """
        asked = prep.contact_wait.activated_at if prep.contact_wait is not None else None
        deadline = (asked or prep.started) + self.meta_budget + self.probe_budget + 5.0
        if limit:
            deadline = min(deadline, limit)
        while not prep.ready.wait(0.2):
            progress.phase(f"{prefix}{prep.phase}")
            if self.clock() > deadline:  # поток сам не уложился - не ждём вечно
                prep.error = prep.error or f"фаза «{prep.phase}» не уложилась в бюджет"
                return

    def _peek(self, prep: _Prep, progress: Progress, deadline: float, phase: str) -> bool:
        """Заглянуть в подготовку с коротким сроком: успела — ``True``, нет — ``False``.

        Отличие от :meth:`_wait` не в сроке, а в последствиях: этот срок наш, а не
        релиза, и просроченному прогреву :attr:`_Prep.error` не ставится. Иначе
        подглядывание за соседом молча делало бы его негодным.
        """
        while not prep.ready.wait(0.2):
            progress.phase(phase)
            if self.clock() > deadline:
                return False
        return True

    def _honest(
        self,
        plan: _Plan,
        chosen: _Prep,
        queue: list[int],
        args: Args,
        progress: Progress,
        judged: dict[int, str] | None = None,
    ) -> _Prep:
        """Подтверждённое разрешение против обещанного: 574p вместо 1080p — не мелочь.

        Верх отбора — самый обсиженный годный кандидат, и это правило остаётся.
        Но обсиженность считается **среди честных**: если ffprobe уже прочитан и говорит,
        что внутри верха не HD, а рядом в очереди стоит живой релиз, который обещает
        1080p, — стоит спросить у ffprobe и его. Живой случай, ради которого это
        написано: «Моана 2», верх ``WEB-DL-AVC`` 3.14 ГБ / 140 сидов оказался 1150×574,
        а вторым лежит настоящий 1080p 13.3 ГБ со 121 сидом.

        Платим за проверку немного: запасной греется с той же секунды, что и верх
        (:meth:`resolve` поднимает следующего сразу), поэтому ждём не прогрев, а разницу
        двух ffprobe, и не дольше :data:`HONEST_BUDGET`.

        Молчаливых подмен нет в обе стороны: и подмена, и отказ от неё печатают строку.
        ``--release N`` и ``--file N`` не трогаем вовсе — там человек выбрал сам.

        🔴 TC-194. ``judged`` - приговоры, уже вынесенные очередью отбора (:meth:`resolve`).
        Без него проверка переспрашивала тех, кого сама же только что забраковала: их
        подготовка лежит в :attr:`preps` готовой, ``ffprobe`` прочитан, и тот же
        :meth:`_trouble` с теми же порогами возвращал тот же приговор - вторая одинаковая
        строка на экране («Сталкер»: два решения, четыре строки) и ни одной новой записи в
        следе. Заодно этим съедались места в :data:`MAX_TRIES`, и до по-настоящему
        непроверенных соседей проверка не доходила.

        🔴 TC-492. Второго повода - «язык звука не назван» (TC-301) - тут больше нет, и
        убран он не отказом от него, а тем, что повод перестал существовать: сюда доходит
        только релиз с ПОДТВЕРЖДЁННОЙ русской дорожкой (:func:`voice_unproven`), а
        безымянный паспорт теперь бракуется гейтом и очередь идёт дальше сама. Спросить
        соседа, обещавшего русскую именем, отдельной машинкой больше незачем: он и так
        стоит в очереди, и ранжир поднимает его над молчаливыми (:func:`sound_step`).
        """
        if args.release is not None or args.pinned:
            return chosen
        judged = judged or {}
        short = understated(chosen.release, chosen.found)
        if not short:
            return chosen
        why_look = short
        # Очередь целиком тут не спрашивается: каждый вопрос - это ещё одна раздача в
        # TorrServer, то есть кэш и полоса роя у того, кого мы и так вот-вот покажем.
        rest = [
            n
            for n in queue
            if n != chosen.number
            and n not in judged
            and promises_more(plan.ranked[n - 1], chosen.found)
        ][:MAX_TRIES]
        deadline = self.clock() + self.honest_budget
        for number in rest:
            # Нужны двое: тот, кого играем, если проверка ничего не найдёт, и тот, кого
            # спрашиваем сейчас. Проверенные и отвергнутые убираются тут же, ниже.
            self.needed = {(plan.picture.key, chosen.number), (plan.picture.key, number)}
            alt = self.start(plan, number)
            self._ask(plan, alt, [number])
            phase = f"релиз {chosen.number} {why_look} - смотрю {number}"
            if not self._peek(alt, progress, deadline, phase):
                progress.phase("")
                _turned_down(judged, number, "не успел ответить")
                print(f"релиз {number} не успел ответить - играю {chosen.number} ({why_look})")
                # Спросили и ждать перестали - значит, ответ больше не нужен, а раздача
                # соседа осталась бы висеть до общей уборки, доедая полосу у того, кого мы
                # сейчас играем. Отпускаем сразу и по своему хэшу; подъём, который ещё
                # идёт в его потоке, уберёт себя сам (:meth:`_work`, ветка ``dropped``).
                self._forget(alt)
                return chosen
            progress.phase("")
            why = self._trouble(
                alt,
                pinned=False,
                warn_mbit=plan.warn_mbit,
                recode=plan.recode_at > 0,
                hard_mbit=plan.hard_mbit,
            )
            if why:
                _turned_down(judged, number, why)
                print(f"релиз {number} не годится ({why})")
                self._forget(alt)  # спросили и получили ответ - держать его больше незачем
                continue
            # 🔴 TC-178. Честный 1080p без русской дорожки - это не «лучше»: разрешение
            # выиграно, а картина осталась несмотренной. Взятый сюда доходит только с
            # ПОДТВЕРЖДЁННОЙ русской дорожкой, и менять её на кадр нельзя - в том числе на
            # кадр релиза, чей паспорт про язык промолчал (TC-492): это тот же размен
            # знания на незнание, только в профиль.
            if voice_unproven(alt.found, native=plan.picture.native):
                _turned_down(judged, number, "без русской озвучки")
                print(f"релиз {number} не лучше (без русской озвучки)")
                self._forget(alt)
                continue
            if not honest_shot(alt.release, alt.found) or alt.found.frame <= chosen.found.frame:
                _turned_down(judged, number, f"не лучше ({quality_text(alt.release, alt.found)})")
                print(f"релиз {number} не лучше ({quality_text(alt.release, alt.found)})")
                self._forget(alt)
                continue
            print(f"релиз {chosen.number} {short} - беру {number} (настоящий {alt.found.quality})")
            self._forget(chosen)  # верх больше не нужен: полосу роя доедать ему незачем
            return alt
        print(f"релиз {chosen.number} {short} - честнее рядом нет, играю его")
        return chosen

    def _trouble(
        self,
        prep: _Prep,
        pinned: bool,
        warn_mbit: float = 0.0,
        recode: bool = False,
        hard_mbit: float = 0.0,
    ) -> str:
        """Почему релиз не годится; пусто — годится. Названный руками не подменяется.

        Битрейт здесь считается **по прочитанному файлу**, а не по размеру раздачи, и это
        разные числа: у «Моаны 2» прикидка (:func:`bitrate_of`) делит 13.3 ГБ на типовые
        два часа и даёт 14.8 Мбит/с, а внутри — фильм на 1:39:37, то есть честные
        17.8 Мбит/с, на которых Q70D встаёт в ребуфер раз в 30–60 с.
        Прикидка потолка при выборе дефолта такой релиз пропускала и пропускать будет:
        до ffprobe длительности картины не знает никто. Поэтому потолок проверяется ещё
        раз — тем же числом, которое показ печатает пользователю.

        ⚠️ ``warn_mbit`` здесь — это ``bitrate_hard_mbit``, а не потолок декодера:
        тяжёлые куски перекодируются, и «Моана 2» на 19 Мбит/с теперь годится.
        Отбраковывается только то, что перекодированием не спасти.

        ⚠️ Само число берётся из **паспорта** — веса видеодорожки, — а не из размера
        файла (:meth:`torrcast.stream.Media.weight_mbit`). Отбраковка спрашивает
        «сколько придётся перекодировать», а десять озвучек и двенадцать субтитров
        перекодировать не придётся: они на ТВ не уезжают вовсе.

        ⚠️ **HEVC больше не отказ** (``recode``): такой файл перекодируется целиком
        (:data:`torrcast.stream.RECODE_CODECS`), и аниме — жанр, где HEVC бывает вообще
        всем, что нашлось, — теперь играет. Предпочтение H.264 при прочих равных живёт
        не здесь, а в ранжире (:func:`rank_releases` топит hevc ниже всех), то есть
        сплошной перекод достаётся ровно тем релизам, у которых альтернативы нет.

        🔴 TC-221/TC-222. Кадр выше того, что берёт приёмник, здесь больше НЕ отказ:
        сплошной перекод ужимает его вниз (:attr:`torrcast.profile.Profile.recode_frame`),
        и 2160p играется в 1080p. Прежний отказ стоял на объяснении «перекод 4К не
        успевает», а замер TC-157 его перевернул: со скейлом до 1080p тот же перекод идёт
        1.53x реального времени против 1.03x без скейла. Отказ остаётся ровно там, где
        ужать нечем, - при выключенном перекодировании.

        ⚠️ ``hard_mbit`` - потолок для тех, кого сплошной перекод не вытягивает
        (:attr:`torrcast.state.Config.bitrate_hard_mbit`), и кадру выше 1080p он достаётся
        по-прежнему. Причина теперь не в скорости, а в запасе: у ужатого 4К она 1.34-1.41x
        (замер 09-08-2026 на тяжёлом месте) против 3.4x у 1080p, и тянуть из роя при этом
        надо ровно столько, сколько весит исходник. Рост кадра тут знает ffprobe, а не имя
        раздачи, поэтому 4K-ремукс с молчаливым именем ловится именно на этой ступени.
        """
        if prep.error:
            return prep.error
        if prep.media is None or prep.video is None:
            return "поток не прочитан"
        if not pinned and warn_mbit > 0:
            peak = prep.media.weight_mbit(prep.video.size)
            ceiling = warn_mbit
            # Причину отказа называем по ситуации. Обычный потолок - свойство
            # приёмника. А потолок, опущенный по высоте кадра (RECODE_HEIGHT), -
            # это скорость перекода НАШЕЙ машины: кадр выше 1080p в реальное время
            # не укладывается, и винить тут приёмник - нечестно.
            reason = "слишком тяжёлый для приёмника"
            if hard_mbit > 0 and prep.media.height > RECODE_HEIGHT:
                ceiling = min(warn_mbit, hard_mbit)
                reason = "перекод такого кадра этой машине не по силам"
            if peak > ceiling:
                return f"{reason}, ~{peak:.0f} Мбит/с"
        # ⚠️ Имя кодека тут не последнее слово: Hi10P зовётся ``h264``, а приёмник его не
        # берёт (:meth:`torrcast.profile.Profile.verdict`). При выключенном перекодировании
        # такой релиз - честный отказ отбора наравне с HEVC, и назван он своим именем:
        # «h264» в строке «не подошёл» человека бы только запутало.
        codec = prep.media.video_name or "h264"
        # 🔴 Судьба картинки решается ОДНИМ вызовом и в одном месте на весь код: копия,
        # сплошной перекод или честный отказ (:meth:`torrcast.profile.Profile.verdict`).
        # Белый список кодеков и глубина цвета - свойство ПРИЁМНИКА, а не показа: они
        # приходят из его профиля (:mod:`torrcast.profile`).
        call = self.profile.verdict(prep.media.video or "", prep.media.depth, prep.media.frame)
        if pinned or call == COPY:
            return ""
        if call == REFUSE:
            # vp9, av1, vc1, mpeg2video: копией их приёмник не играет, а цена сплошного
            # перекода для них не мерена. Честный отказ и следующий релиз - это не
            # «мы не осилили», а «есть кандидат, про которого мы знаем всё».
            return codec
        if recode:
            return ""
        # 🔴 TC-221. Перекодирование выключено, а копией это не уедет - и причина у отказа
        # бывает двух разных сортов. Кодек с глубиной («hevc», «h264 10 бит») человеку всё
        # объясняет сам, а вот 2160p H.264 8 бит - это обычный кодек, и слово «h264» в
        # строке «не подошёл» только запутало бы: не подошёл кадр. Ужать его вниз мог бы
        # перекод (:attr:`Profile.recode_frame`), но его-то и выключили.
        if prep.media.frame > self.profile.recode_frame and self.profile.plays_copy(
            prep.media.video or "", prep.media.depth
        ):
            return f"{prep.media.quality} - такой кадр приёмнику только через перекод"
        return codec

    def _forget(self, prep: _Prep) -> None:
        """Убрать раздачу из TorrServer: она либо не подошла, либо больше не нужна.

        Кроме одного случая: её держит живой показ - параллельный ``cast`` греет ту же
        выдачу, и снос чужой раздачи выдернул бы источник из-под экрана
        (:func:`_held_by_show`).
        """
        prep.dropped = True
        if prep.torrent_hash and not _held_by_show(prep.torrent_hash):
            self.torrserver.drop(prep.torrent_hash)

    def drop_all(self) -> None:
        """Показа не будет: всё прогретое убирается из TorrServer.

        Выходов мимо :meth:`keep_only` хватает — Ctrl-C на вопросе «Что смотрим?», запуск
        без терминала, «годного релиза нет», ``--dry`` (ему сносится и ВЫБРАННАЯ раздача:
        :meth:`keep_only` к тому месту уже прошёл, и живой остаётся ровно она). Раздачи
        при этом уже добавлены и тянут кэш в RAM до перезапуска TorrServer: ``save_to_db``
        у них выключен, но живут они не в нашем процессе, и умирают не вместе с ним.
        """
        for prep in self.preps.values():
            if not prep.dropped:  # убранное потолком или keep_only второй раз не трогаем
                self._forget(prep)

    def keep_only(self, chosen: _Prep) -> None:
        """Оставить в TorrServer одну раздачу — ту, которую показываем.

        Прогрев по определению греет лишнее: топ-3 картины франшизы и запасной релиз.
        Всё лишнее обязано исчезнуть до старта показа, иначе оно доедает и кэш в RAM,
        и полосу роя, а показ идёт ровно на них (и tmpfs не должен расти без предела).
        """
        for prep in self.preps.values():
            if prep is not chosen:
                self._forget(prep)

    def _work(self, plan: _Plan, prep: _Prep) -> None:
        """Фоновая подготовка: раздача в TorrServer, метаданные по DHT, ffprobe."""
        try:
            prep.phase = "метаданные (DHT)"
            prep.torrent_hash = self.torrserver.add(prep.release.magnet)
            files = self.torrserver.wait_files(
                prep.torrent_hash,
                timeout=self.meta_budget,
                grace=prep.contact_wait or 0.0,
            )
            prep.files = files
            prep.meta = self.clock() - prep.started
            journal().mark("метаданные", релиз=prep.number, картина=plan.picture.key)
            prep.video = self.choose(plan, prep.release, files)
            prep.phase = "дорожки"
            began = self.clock()
            source = self.torrserver.stream_url(prep.torrent_hash, prep.want.index)
            # Всё, что показ прочитает из роя первым, читается здесь и сейчас: карта
            # опорных кадров (без неё нет сетки) и начало файла (его читает ffmpeg). Это
            # самая ранняя секунда, когда известен файл, - то есть параллельно и ffprobe,
            # и вопросам человека. Показ потом либо берёт готовое, либо
            # дожидается этого же чтения, а не начинает своё вторым потоком.
            warm_file(source, alive=lambda: not prep.dropped, name=prep.want.name)
            prep.media = self.prober(
                source,
                timeout=self.probe_budget,
                alive=(
                    None
                    if prep.patient
                    else swarm_pulse(source, SWARM_GRACE, wait=prep.contact_wait)
                ),
            )
            prep.read = self.clock() - began
            journal().mark("ffprobe", релиз=prep.number, картина=plan.picture.key)
            prep.phase = "готово"
        except TorrcastError as exc:
            prep.error = str(exc)
            prep.failure = exc
            prep.phase = "сбой"
        finally:
            prep.ready.set()
            if prep.dropped:  # пока грелись, показ ушёл к другому релизу
                self._forget(prep)


__all__ = [name for name in globals() if not name.startswith("__")]
