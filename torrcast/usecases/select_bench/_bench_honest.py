"""Проверка честности верха отбора: подтверждённое разрешение против обещанного."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.pick_settings import MAX_TRIES
from torrcast.ports.progress import Progress
from torrcast.usecases.rank.honest_shot import honest_shot
from torrcast.usecases.rank.promises_more import promises_more
from torrcast.usecases.rank.quality_text import quality_text
from torrcast.usecases.rank.understated import understated
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import _turned_down
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench._bench_trouble import _BenchTrouble

if TYPE_CHECKING:
    from torrcast.domain.args import Args


class _BenchHonest(_BenchTrouble):
    """Проверка честности верха отбора."""

    def _honest(
        self,
        plan: Plan,
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
