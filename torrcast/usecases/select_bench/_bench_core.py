"""Ядро стенда: заведённые прогревы, место под них и уборка за собой."""

from __future__ import annotations

import time
from collections.abc import Callable

import torrcast.usecases.select_bench._bench_state as _bench_state
from torrcast.domain.media import Media
from torrcast.domain.pick_settings import (
    HONEST_BUDGET,
    META_BUDGET,
    PICK_BUDGET,
    PROBE_BUDGET,
    VERDICT_BUDGET,
)
from torrcast.domain.prewarm_settings import MAX_LIVE
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.torrent_engine import TorrentEngine
from torrcast.usecases.playback.file_picker import _default_file
from torrcast.usecases.rank.peer_grace import peer_grace
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.torrents import _held_by_show


class _BenchCore:
    """Состояние стенда и всё, что его заводит и убирает."""

    def __init__(
        self,
        torrserver: TorrentEngine,
        choose: Callable[[Plan, Release, list[TorrFile]], TorrFile] | None = None,
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
        self.prober = prober or _bench_state._bench_prober
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

    @staticmethod
    def _ask(plan: Plan, prep: _Prep, queue: list[int]) -> None:
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
