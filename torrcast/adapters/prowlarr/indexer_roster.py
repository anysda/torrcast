"""Список индексеров Prowlarr и его же список тех, кого спрашивать нельзя."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Final

from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.failed_just_now import failed_just_now
from torrcast.domain.heal_due import heal_due
from torrcast.domain.indexer_budget import EXTRA_TIMEOUT
from torrcast.domain.infra_error import InfraError

_INDEXERS_PATH: Final = "/api/v1/indexer"
#: Кого Prowlarr увёл в недоступные: список из одних заблокированных, с полями
#: ``indexerId``, ``disabledTill`` и ``mostRecentFailure``. Отпустивших он не показывает,
#: поэтому «пусто» тут и значит «бана нет».
_STATUS_PATH: Final = "/api/v1/indexerstatus"
#: Проверка одного индексера: POST с его же телом из :data:`_INDEXERS_PATH`. Успех
#: снимает истёкшую отсрочку; активную не проверяем, потому что отказ начинает её заново.
_TEST_PATH: Final = "/api/v1/indexer/test"
#: Список индексеров - локальная страница Prowlarr, сеть в ней не участвует.
LIST_TIMEOUT: Final = 15.0
#: Чем поднимается лечебный стук: работа отдаётся в сторону и круга не держит.
_Spawn = Callable[[Callable[[], None]], None]


def _aside(work: Callable[[], None]) -> None:
    """Боевой подъём лечебного стука: демон с именем, по которому его видно в отладке."""
    threading.Thread(target=work, daemon=True, name="idx-heal").start()


class IndexerRoster:
    """Кто у Prowlarr включён, кого он увёл в недоступные и как вернуть выбывшего."""

    def __init__(self, api: ProwlarrApi, spawn: _Spawn = _aside) -> None:
        self.api = api
        #: Чем отдаётся в сторону лечебный стук (:meth:`_heal`). Боевой путь уводит его в
        #: демон-поток; зеркалу отдельный поток не нужен - ему нужен ответ про стук, а не
        #: про планировщик, и со своим ``spawn`` оно получает его тем же кругом.
        self._spawn = spawn
        self._indexers: tuple[Indexer, ...] | None = None

    def known(self) -> tuple[Indexer, ...]:
        """Включённые индексеры (номер, имя); пусто - спрашивать придётся общим запросом."""
        if self._indexers is None:
            try:
                payload = self.api.get_json(self.api.url(_INDEXERS_PATH), LIST_TIMEOUT)
            except InfraError:
                return ()
            if not isinstance(payload, list):
                return ()
            self._indexers = tuple(
                (int(i["id"]), str(i.get("name") or i["id"]))
                for i in payload
                if isinstance(i, dict) and i.get("enable") and str(i.get("id", "")).isdigit()
            )
        return self._indexers

    def usable(self, known: Sequence[Indexer]) -> tuple[tuple[Indexer, ...], tuple[str, ...]]:
        """Кого из списка можно спросить и кого Prowlarr увёл в недоступные (TC-259).

        Заблокированного спрашивать нельзя: вместо выдачи придёт отказ ВСЕГО поиска, а
        места в круге и личного бюджета он стоит как живой. Взамен в него стучится
        лечение (:meth:`_heal`), и починившееся звено возвращается следующим же поиском.

        Заблокированы все до одного - каталога сейчас нет, и это отказ инфры, а не пустой
        поиск: «ничего не нашлось» про полку, которую не открывали, сказать нельзя.
        """
        blocked = self.blocked()
        self._heal(blocked)
        banned = tuple(name for num, name in known if num in blocked)
        usable = tuple(pair for pair in known if pair[0] not in blocked)
        if not usable:
            raise InfraError(phrase("prowlarr.all_indexers_unavailable", names=", ".join(banned)))
        return usable, banned

    def blocked(self) -> dict[int, tuple[str, str]]:
        """Кого Prowlarr увёл в недоступные: номер - отказ и срок отсрочки.

        🔴 TC-259. Включённый и доступный - разные вещи, а по списку индексеров
        (:meth:`known`) их не различить: забаненный так и стоит ``enable: true``.
        Спросить его при этом нельзя - персональный запрос вернёт не выдачу, а отказ
        всего поиска («all selected indexers being unavailable»), то есть ровно то же,
        что вернул бы мёртвый Prowlarr. Отсюда и путаница в замерах: индексер числился
        мёртвым, хотя мёртв был не он, а наше право его спрашивать.

        Отказ этой страницы - не отказ поиска: не прочитали статус, значит идём кругом
        как раньше, вслепую. Хуже, чем было, от этого не станет.
        """
        try:
            payload = self.api.get_json(self.api.url(_STATUS_PATH), LIST_TIMEOUT)
        except InfraError:
            return {}
        if not isinstance(payload, list):
            return {}
        return {
            int(item["indexerId"]): (
                str(item.get("mostRecentFailure") or ""),
                str(item.get("disabledTill") or ""),
            )
            for item in payload
            if isinstance(item, dict) and str(item.get("indexerId", "")).isdigit()
        }

    def refused(self, banned: Sequence[str], since: float) -> tuple[str, ...]:
        """Кто отказал ПОКА ШЁЛ этот поиск, спрятав отказ за пустой выдачей (TC-291).

        Спрашиваем ту же страницу, что и :meth:`blocked`, но ПОСЛЕ круга, а не до: до
        круга отметки ещё нет - её ставит сам отказ. Живой замер показал, что ставится
        она в тот же миг, в который нам приходит ``200 []``, так что окна между ложью и
        её уликой нет вовсе.

        Уже забаненных отсюда убираем нарочно: их мы и не спрашивали, а отметку им мог
        обновить наш же лечебный стук - обвинить круг в чужом отказе значило бы соврать
        во вторую сторону.

        Лишним походом это не становится: зовётся ровно там, где выдача пуста, то есть
        там, где мы и так собираемся что-то заявить о каталоге. На пути к картинке этого
        запроса нет.
        """
        names = dict(self.known())
        if not names:
            return ()
        return tuple(
            name
            for num, (failed, _disabled) in sorted(self.blocked().items())
            if (name := names.get(num, ""))
            and name not in banned
            and failed_just_now(failed, since)
        )

    def _heal(self, blocked: dict[int, tuple[str, str]]) -> None:
        """Постучаться в заблокированные индексеры - вдруг источник уже вернулся.

        🔴 TC-272. Prowlarr снимает бан по своим часам, а не по здоровью источника, и
        каталог возвращается не когда звено починилось, а когда истечёт отсрочка (замер:
        канал пропал на 12 с - каталог был урезан 59.2 с ПОСЛЕ его возврата; на хронике
        отсрочка дорастает до часа). Ручки «снять бан» у Prowlarr нет
        (``DELETE /api/v1/indexerstatus`` отвечает 405), но есть :data:`_TEST_PATH`: он
        ходит в источник по-настоящему, и УСПЕХ гасит отсрочку - тот же замер с лечением
        дал 10.6 с вместо 59.2. Честность тут держится сама собой: бан снимает не наша
        просьба, а ответ источника; мёртвый источник так и останется мёртвым.

        Круга это не держит: стучимся отдельным потоком, как и опоздавшие (TC-118), а
        плодами пользуется уже следующий поиск. Ждать смысла нет - выдача заблокированного
        в этот круг всё равно не попадёт.
        """
        now = time.time()
        due = tuple(
            num for num, (failed, disabled) in blocked.items() if heal_due(failed, disabled, now)
        )
        if not due:
            return
        self._spawn(lambda: self._knock(due))

    def _knock(self, nums: tuple[int, ...]) -> None:
        """Стук в заблокированные - строго по одному, друг за другом.

        Параллель тут запрещена нарочно: лишние одновременные запросы к одному трекеру
        и есть та причина, по которой Prowlarr раздаёт баны (Nyaa отвечает на них 504).
        Лечить бан способом, которым он ставится, - худшее, что можно придумать.
        """
        for num in nums:
            self.api.probe(
                self.api.url(f"{_INDEXERS_PATH}/{num}"),
                self.api.url(_TEST_PATH),
                LIST_TIMEOUT,
                EXTRA_TIMEOUT,
            )


__all__ = ["LIST_TIMEOUT", "IndexerRoster"]
