"""Очередь отбора по одной картине: кого спрашивать, в каком порядке и кого не спрашивать."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from torrcast.domain._series import _Series
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.episode import Episode
from torrcast.domain.info_hash import info_hash
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.misses_episode import misses_episode
from torrcast.usecases.select._plan_fields import _PlanFields

if TYPE_CHECKING:
    from torrcast.domain.args import Args


@dataclass(slots=True)
class Plan(_PlanFields):
    """Что покажем по одной картине: пул релизов и, для сериала, нужная серия.

    План строится на **все** картины франшизы ещё до вопроса — иначе прогрев под меню
    невозможен: греть надо то, что человек, скорее всего, выберет. Поля плана живут
    в :class:`torrcast.usecases.select._plan_fields._PlanFields`, здесь - очередь отбора.
    """

    def candidates(self, args: Args) -> list[int]:
        """Очередь релизов: прошедшие ворота, в порядке ранжира - **все, сколько есть**.

        Обрезать очередь тут больше нечем: сколько раздач успеет разобрать показ, решают
        не эти строки, а :meth:`Bench.resolve` — по приговорам (:data:`MAX_TRIES`) и по
        часам (:data:`PICK_BUDGET`). Пока очередь резалась тремя номерами, отбор сдавался
        со словами «годного релиза нет» ровно тогда, когда рядом в ней стояли живые: в
        замере на тысяче запросов перепроверка в один поток оживляла шесть картин из
        восьми, у которых три раздачи подряд промолчали пирами.

        🔴 TC-432. Ворота проходят ВСЕ, включая верх ранжира. До сих пор он вставал в
        очередь безусловно, и мимо ворот проходил ровно он: «Ведьмак 3: Дикая Охота»
        (игра, ``kind=other``, 35.6 ГБ) стояла единственным кандидатом своей картины на
        запрос «ведьмак s2e4», а «Ван Пис - 923» с нулём сидов - на запрос s1e1. Это
        подмена картины, худший вид брака: человек просит серию сериала, а наверх
        очереди встаёт игра. Ворота при этом отсекают правильно (замер TC-377 по тому
        же корпусу: ложных отсевов ноль) - работать оставалось ровно одно место.

        Безусловной остаётся одна очередь - названная человеком (``--release N``): это
        его явное решение, а не подмена, и судить его воротами нечего.

        Огрызков в очереди нет вовсе (:func:`misses_episode`): тратить на них метаданные
        по DHT незачем — раздача уже своим именем сказала «нужной серии тут нет», и это
        5-40 с за заранее известный отказ. Отбраковка не молчаливая: кого выкинули,
        печатает :attr:`skipped`.

        При открытых воротах (:attr:`loose`) в очередь идут и молчаливые имена: у
        картины иначе нет ни одного живого кандидата, а судить молчание всё равно
        может только ffprobe — и он его тут же и судит.

        При открытых воротах последней надежды (:attr:`last_resort`) к ним добавляется
        названный HEVC до 1080p включительно (:func:`hevc_hope`): играть его будет
        сплошной перекод, и берётся он ровно тогда, когда живого кандидата с нужной
        серией нет вообще.

        Очередь может оказаться пустой - и это ответ, а не повод подставить отсеянное:
        отказ с перечнем причин печатает :meth:`Bench.resolve` (:func:`unfit_line`).
        """
        if args.release is not None:
            if args.release_hash:
                number = next(
                    (
                        number
                        for number, release in enumerate(self.ranked, start=1)
                        if info_hash(release) == args.release_hash
                    ),
                    None,
                )
                if number is None:
                    raise NotFoundError(
                        phrase(
                            "select.release_missing_new_listing",
                            release=args.release,
                            title=self.picture.title,
                        )
                    )
                return [number]
            if not 1 <= args.release <= len(self.ranked):
                # 🔴 TC-446. Номер относится к ЭТОЙ картине - той, что человек выбрал в
                # меню или назвал флагом --pick, - и отказ её называет. Безымянный счёт
                # читался как счёт всей выдачи, а считался по одной картине из неё.
                raise NotFoundError(
                    phrase(
                        "select.release_number_missing",
                        title=self.picture.title,
                        total=len(self.ranked),
                        release=args.release,
                    )
                )
            return [args.release]
        queue = [
            n
            for n, r in enumerate(self.ranked, start=1)
            if is_candidate(
                r,
                self.runtime,
                self.warn_mbit,
                self.loose,
                self.hard_mbit,
                self.last_resort,
                self.copy_hevc,
            )
            and not misses_episode(r, self.want)
        ]
        queue += self._dubbed_tail(queue)
        # 🔴 Раздача, которая в этом запуске уже не сыграла, из очереди ВЫБЫВАЕТ, а не
        # понижается: при пуле длиной один понижение вернуло бы её же, и зритель получил бы
        # ту же темноту второй раз подряд (:meth:`torrcast.domain.args.Args.buried`).
        return [n for n in queue if not args.buried(self.ranked[n - 1].magnet)]

    def series_in(self, release: Release, files: list[TorrFile]) -> _Series | None:
        """Вернуть серии плана или признать их по нумерованным файлам раздачи."""
        if self.series is not None or self.picture.kind != "movie":
            return self.series
        if not map_episodes(files, release.season, explicit_only=True):
            return None
        return _Series(want=Episode(1, 1))

    def recognize_series(self, release: Release, files: list[TorrFile]) -> None:
        """Записать вид, доказанный метаданными уже выбранной раздачи."""
        found = self.series_in(release, files)
        if found is None or self.series is not None:
            return
        self.picture.kind = "tv"
        self.series = found

    def _dubbed_tail(self, queue: list[int]) -> list[int]:
        """Хвост очереди: русские раздачи, которых ворота отбора не пустили внутрь.

        🔴 TC-195. Ворота (:func:`is_candidate`) судят ИМЯ раздачи, и раздача, чьё имя
        молчит о качестве, кандидатом не становится, пока у картины есть живой ИМЕННОЙ
        кандидат (:attr:`loose`). Ровно на этом вечер зрителя и кончился: у «Тачек»
        2006 года очередь состояла из ОДНОГО релиза - названного 1080p H.264 на 66 сид,
        - его рой промолчал, и показ отказал строкой «раздач в выдаче 5, потрогали 1 -
        до остальных отбор не дошёл». А среди четырёх нетронутых лежали две с дубляжом
        (4.4 ГБ на 3 и на 1 сид), которых никто не спрашивал.

        Отказ был честен про то, что потрогали, и бесполезен для человека: картина в
        каталоге есть, русская дорожка у неё есть, а на экране пусто.

        Хвост, а не послабление ворот, - и это главное. Порядок головы очереди не
        меняется ни на знак: дефолт тот же, запасные те же, и на картине, где голова
        играет, хвоста не видно вовсе - до него просто не доходят. Значит и время до
        картинки прежнее. Меняется ровно один случай: голова кончилась, а показывать
        нечего.

        В хвост идёт только то, у чего РУССКАЯ дорожка названа именем
        (:attr:`~torrcast.domain.release.Release.dubbed`): молчание про качество мы простить
        готовы - его рассудит ffprobe, - а молчание про язык прощать нечему, иначе
        хвост натащил бы англоязычных рипов туда, где человек ждёт перевод. Потолок
        битрейта и образы дисков хвост не двигает: там ресивер встаёт и играть нечего.
        """
        seen = set(queue)
        return [
            n
            for n, r in enumerate(self.ranked, start=1)
            if n not in seen
            and r.dubbed
            and not misses_episode(r, self.want)
            and is_candidate(
                r, self.runtime, self.warn_mbit, True, self.hard_mbit, True, self.copy_hevc
            )
        ]

    @property
    def want(self) -> Episode | None:
        """Нужная серия, если картина — сериал; у фильма серии нет."""
        return self.series.want if self.series else None

    @property
    def skipped(self) -> list[Release]:
        """Раздачи, отбракованные до каста: нужной серии в них нет по их же именам."""
        return [r for r in self.ranked if misses_episode(r, self.want)]
