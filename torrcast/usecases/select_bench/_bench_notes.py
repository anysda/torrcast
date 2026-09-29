"""Строки перед стартом и запасной ход, когда искомой озвучки нет ни у кого."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.recode_note import recode_note
from torrcast.ports.journal.slot import journal
from torrcast.usecases.choice.last_hope_note import last_hope_note
from torrcast.usecases.rank.heard import heard
from torrcast.usecases.rank.stepdown_note import stepdown_note
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench._bench_honest import _BenchHonest

if TYPE_CHECKING:
    from torrcast.domain.args import Args


class _BenchNotes(_BenchHonest):
    """Что стенд говорит человеку перед стартом."""

    def _announce(
        self,
        plan: Plan,
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
        plan: Plan,
        mute: _Prep,
        queue: list[int],
        judged: dict[int, str],
        reached: int,
        tried: int,
    ) -> _Prep:
        """Запасной ход: дорожки на языке зрителя не нашлось ни у кого - играем то, что есть.

        🔴 TC-178. Гейт озвучки нельзя делать слепым. Дорожка на языке зрителя - условие
        годности релиза, но у картины её может не быть НИ У КОГО: японский тайтл, который
        никто не озвучивал, старое кино, чужой сериал. Отказать в такой картине значило бы
        отобрать у человека и то, что есть, - а он про неё ничего плохого не спрашивал.

        Поэтому ступеней две. Пока в очереди есть кого спросить, безрусский релиз ждёт в
        стороне (его раздача при этом не убирается - иначе запасной ход стоил бы второго
        подъёма с нуля). Кончилась очередь - он играет, и решение это громкое: строка на
        экране, запись в недельном следе (по ней замер и считает дыры каталога) и честная
        строка про язык звука перед стартом (:func:`sound_note`).

        🔴 TC-741. Третий ответ паспорта - «язык не назван» - сюда больше не приходит.
        Ходом этот случай не отличался бы ничем, а строка про него честной быть не может:
        «звук не назван» - это признание, что мы не знаем, что зазвучит, и назвать его
        зрителю нечем. Такой релиз остаётся забракованным (:meth:`_Tally.hold`), и
        картина, у которой всё найденное молчит про язык, кончается отказом со своим
        именем, а не тихой подстановкой первой дорожки файла.

        🔴 TC-968. Ходом этим кончается не только ИСЧЕРПАННАЯ очередь, но и обход, у
        которого кончился потолок поиска дорожки (:data:`VOICE_BUDGET`). Правило TC-741 -
        «срезанный потолком запасного хода не получает» - написано про потолки посторонние:
        часы фазы и приговоры ffprobe сбивают обход с пути бедами, к языку отношения не
        имеющими, и про хвост очереди он тогда не знает ничего. Потолок поиска дорожки -
        другой случай: обход шёл по хвосту ровно с этим вопросом, получал на него один и
        тот же ответ и остановлен не бедой, а ценой. Замер стенда 01-09-2026: половина
        времени до картинки уходила на мёртвые рои, спрошенные только про звук, и кончалось
        это всё равно здесь - тем же запасным ходом и той же строкой про японский звук.

        Тихой подмены языка тут по-прежнему нет ни на шаг: ход громкий, строка называет
        язык до старта, а сколько раздач успели спросить - говорит она же (``tried``).

        Проверки честности (:meth:`_honest`) тут нет намеренно: она меняет релиз ради
        разрешения, а на этом пути мы уже знаем, что искомой дорожки нет ни у одного из
        проверенных, и второй круг ffprobe стоил бы секунд ровно за то же самое.
        """
        lang = heard(mute.found)
        journal().emit("select", "mute", release=mute.number, lang=lang, checked=tried)
        print(phrase("select_bench.mute_fallback_note", tried=tried, number=mute.number, lang=lang))
        # 🔴 TC-1303. Помечаем ход, а не только печатаем строку в stdout: карточка веба
        # печатное слово не читает, и без этого признака зритель молча получал бы чужой
        # звук (см. :class:`web.heard.Heard`, :func:`web.release_keys.release_keys`).
        mute.voice_fallback, mute.voice_checked = True, tried
        self._announce(plan, mute, queue, judged, reached)
        return mute

    def _card_mute(self, plan: Plan, args: Args, queue: list[int]) -> _Prep | None:
        """Запасной ход карточки этой картины: показ, забравший её стенд, очередь не обходит.

        Карточка уже спросила очередь о русском звуке и сыграла бы чужой. «Призрак в
        доспехах» s1e1: карточка обошла очередь за 19.5 с и кончила японским №2, показ
        обошёл её заново по кругу, который опоздавший индексер пересчитал (30 раздач стало
        40), взял немую 384p, и кадра не было вовсе. Беда под профилем
        показа возвращает обход.
        """
        self._recount(plan)
        for (key, number), prep in list(self.preps.items()):
            mine = key == plan.picture.key and prep.card_warmed and prep.voice_fallback
            if args.pinned or not mine or prep.dropped or number not in queue:
                continue
            recode, warn, hard = plan.recode_at > 0, plan.warn_mbit, plan.hard_mbit
            if self._trouble(prep, pinned=False, warn_mbit=warn, recode=recode, hard_mbit=hard):
                return None
            return self._mute_fallback(plan, prep, queue, {}, len(queue), prep.voice_checked)
        return None

    def _recount(self, plan: Plan) -> None:
        """Прогревы картины - на номера этого круга, по магниту: пересчёт номера сдвигает.

        Без переезда :meth:`start` видел под номером чужой магнит и бросал прочитанное
        карточкой, а срок отбора брал готовую раздачу под чужим номером.
        """
        places = {release.magnet: n for n, release in enumerate(plan.ranked, start=1)}
        moved: dict[tuple[str, int], _Prep] = {}
        stale: list[_Prep] = []
        with self._preps_lock:
            for (key, number), prep in self.preps.items():
                if key == plan.picture.key and prep.release.magnet in places:
                    prep.number = number = places[prep.release.magnet]
                elif key == plan.picture.key:
                    stale.append(prep)
                    continue
                moved[(key, number)] = prep
            self.preps = moved
        for prep in stale:
            self._forget(prep)
