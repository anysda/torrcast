"""Ядро стенда: заведённые прогревы, место под них и уборка за собой."""

from __future__ import annotations

import threading
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
    VOICE_BUDGET,
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
from torrcast.usecases.select_bench._bench_keep import KEEP_CEILING, _bench_keep, _Timed
from torrcast.usecases.torrent_claims import CLAIMS
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
        voice_budget: float | None = None,
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
        self.voice_budget = VOICE_BUDGET if voice_budget is None else voice_budget
        self.honest_budget = HONEST_BUDGET if honest_budget is None else honest_budget
        #: Часы отбора: все его сроки меряются отсюда, а не стенными часами напрямую.
        self.clock = clock
        self.preps: dict[tuple[str, int], _Prep] = {}
        #: Прогревы, которые прямо сейчас кому-то нужны и потолком не убираются: тот, чьего
        #: ответа ждут, и тот, который греется ему на смену. Пусто под меню - там нужны все.
        self.needed: set[tuple[str, int]] = set()
        #: До какой секунды часов стенда продлевается срок выбранной раздачи, по хэшу.
        self.keep_until: dict[str, float] = {}
        self.keep_wait: Callable[[float], object] = time.sleep
        self._keep_lock = threading.Lock()

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
        их. Своё в списке тоже видно, но список не различает владельцев.
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

        Кроме двух случаев: её держит живой показ - параллельный ``cast`` греет ту же
        выдачу, и снос чужой раздачи выдернул бы источник из-под экрана
        (:func:`_held_by_show`), - или её держит кто-то ещё в этом процессе: карточка
        страницы и отбор показа (:data:`~torrcast.usecases.torrent_claims.CLAIMS`).
        """
        prep.dropped = True
        torrent_hash = prep.torrent_hash
        if any(other.torrent_hash == torrent_hash for other in self.live()):
            return  # та же раздача у живого прогрева: отбор показа завёл её вторым номером
        adding = (other for other in self.live() if not other.torrent_hash)
        if any(
            not other.ready.is_set() and other.release.magnet == prep.release.magnet
            for other in adding
        ):
            return  # свежий прогрев той же раздачи ещё в ``add``: отметка у стенда общая
        if torrent_hash and CLAIMS.unclaim(torrent_hash, self) and not _held_by_show(torrent_hash):
            self.torrserver.drop(torrent_hash)

    def drop_all(self) -> None:
        """Показа не будет: всё прогретое убирается из TorrServer.

        Выходов мимо :meth:`keep_only` хватает — Ctrl-C на вопросе «Что смотрим?», запуск
        без терминала, «годного релиза нет», ``--dry`` (ему сносится и ВЫБРАННАЯ раздача:
        :meth:`keep_only` к тому месту уже прошёл, и живой остаётся ровно она). Раздачи
        при этом уже добавлены и живут не в нашем процессе, поэтому не умирают вместе с ним.
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
        self._keep_open(chosen)

    def _keep_open(self, chosen: _Prep) -> None:
        """Держать выбранную раздачу открытой, пока её держит стенд (:mod:`._bench_keep`).

        Повторный ``keep_only`` той же раздачи (карточка, потом показ) не заводит второго
        продления, а отодвигает потолок: отсчёт идёт от последнего выбора.
        """
        torrent_hash = chosen.torrent_hash
        if not torrent_hash or not isinstance(self.torrserver, _Timed):
            return  # служба не называет срок закрытия: подделке стенда продлевать нечего
        with self._keep_lock:
            fresh = torrent_hash not in self.keep_until
            self.keep_until[torrent_hash] = self.clock() + KEEP_CEILING
        if fresh:  # поток не держит сам стенд: брошенный стенд уходит сборщику с отметками
            args = (self.torrserver, chosen, self.keep_until, self._keep_lock)
            threading.Thread(
                target=_bench_keep,
                args=(*args, self.clock, self.keep_wait),
                name=f"keep-{torrent_hash}",
                daemon=True,
            ).start()
