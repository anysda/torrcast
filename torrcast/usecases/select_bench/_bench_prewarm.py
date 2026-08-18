"""Прогрев под меню: переезд номеров, уборка чужих картин и запасной релиз."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.pick_settings import MAX_TRIES
from torrcast.domain.prewarm_settings import PREWARM_SPARE
from torrcast.usecases.select._plan import _Plan
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench_recheck import _BenchRecheck

if TYPE_CHECKING:
    from torrcast.domain.args import Args


class _BenchPrewarm(_BenchRecheck):
    """Прогрев под меню и его переезд под новый порядок отбора."""

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
