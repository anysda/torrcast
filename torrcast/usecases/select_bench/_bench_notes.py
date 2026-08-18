"""Строки перед стартом и запасной ход, когда русской озвучки нет ни у кого."""

from __future__ import annotations

from torrcast.domain.recode_note import recode_note
from torrcast.ports.journal import journal
from torrcast.usecases.choice.last_hope_note import last_hope_note
from torrcast.usecases.rank.default_unnamed import default_unnamed
from torrcast.usecases.rank.heard import heard
from torrcast.usecases.rank.stepdown_note import stepdown_note
from torrcast.usecases.select._plan import _Plan
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench._bench_honest import _BenchHonest


class _BenchNotes(_BenchHonest):
    """Что стенд говорит человеку перед стартом."""

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
