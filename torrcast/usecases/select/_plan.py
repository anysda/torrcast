"""Что покажем по одной картине: пул релизов и, для сериала, нужная серия."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from torrcast.domain._series import _Series
from torrcast.domain.episode import Episode
from torrcast.domain.info_hash import info_hash
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.misses_episode import misses_episode
from torrcast.usecases.select._nothing_late import _nothing_late

if TYPE_CHECKING:
    from torrcast.domain.args import Args


@dataclass(slots=True)
class _Plan:
    """Что покажем по одной картине: пул релизов и, для сериала, нужная серия.

    План строится на **все** картины франшизы ещё до вопроса — иначе прогрев под меню
    невозможен: греть надо то, что человек, скорее всего, выберет.
    """

    picture: Picture
    ranked: list[Release]
    runtime: float
    #: Потолок ОТБРАКОВКИ, Мбит/с: выше него релиз не берём вовсе (см. :func:`_plan_for`).
    warn_mbit: float
    series: _Series | None = None
    #: Порог ПЕРЕКОДИРОВАНИЯ, Мбит/с: выше него куски перекодируются, а релиз годен.
    #: Ноль - перекодирование выключено, и тогда отбраковка и порог это одно число.
    recode_at: float = 0.0
    #: Потолок для тех, кого сплошной перекод не спасает, Мбит/с: выше него релиз годен
    #: только при перекоде ЦЕЛИКОМ и только пока кадр не выше 1080p
    #: (:attr:`torrcast.domain.config.Config.bitrate_hard_mbit`). Ноль - ступени нет.
    hard_mbit: float = 0.0
    #: Ворота отбора открыты: живых именных кандидатов у картины нет (:func:`gate_open`),
    #: и молчаливые имена идут в очередь наравне с именными.
    loose: bool = False
    #: Ворота последней надежды открыты: живого кандидата с нужной серией нет ВООБЩЕ
    #: (:func:`last_hope`), и в очередь пускается названный HEVC — играть его будет
    #: сплошной перекод. Перекодирование выключено — ворота закрыты всегда.
    last_resort: bool = False
    #: HEVC объявлен своим ресивером как играющий копией через наш HLS.
    copy_hevc: bool = False
    #: Другие части той же франшизы, до меню не доехавшие: их нет в списке картин, но в
    #: выдаче они есть и раздачи у них живые. Нужны одной строке отказа (:func:`kin_line`).
    kin: list[Picture] = field(default_factory=list)
    #: Запрос назвал СЕРИЮ (``s1e1``), а не просто имя. Тогда тип сказан вслух, и дефолт
    #: обязан считаться среди сериалов (:func:`asked_kind`), а не среди тёзок-полнометражек.
    asked_series: bool = False
    #: :attr:`runtime` — настоящая длительность из справки, а не прикидка (:func:`_timed`).
    runtime_known: bool = False
    #: Раздачи картины, не доехавшие даже до :attr:`ranked`: нужного сезона в них нет по
    #: их же именам. Нужны счёту отсева (:func:`queue_drops`), чтобы он сходился с пулом.
    off_season: int = 0
    #: Выдача опоздавших индексеров: круг ушёл по кворуму, а эти доехали позже (TC-118).
    #: Зовётся ОДИН раз и только после ответа на меню - :func:`_topup`.
    late: Callable[[], list[RawResult]] = _nothing_late

    def candidates(self, args: Args) -> list[int]:
        """Очередь релизов: прошедшие ворота, в порядке ранжира - **все, сколько есть**.

        Обрезать очередь тут больше нечем: сколько раздач успеет разобрать показ, решают
        не эти строки, а :meth:`_Bench.resolve` — по приговорам (:data:`MAX_TRIES`) и по
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
        отказ с перечнем причин печатает :meth:`_Bench.resolve` (:func:`unfit_line`).
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
                        f"показанного релиза {args.release} у «{self.picture.title}» "
                        "в новой выдаче нет"
                    )
                return [number]
            if not 1 <= args.release <= len(self.ranked):
                # 🔴 TC-446. Номер относится к ЭТОЙ картине - той, что человек выбрал в
                # меню или назвал флагом --pick, - и отказ её называет. Безымянный счёт
                # читался как счёт всей выдачи, а считался по одной картине из неё.
                raise NotFoundError(
                    f"у «{self.picture.title}» релизов {len(self.ranked)}, "
                    f"номера {args.release} нет"
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
        return queue + self._dubbed_tail(queue)

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
