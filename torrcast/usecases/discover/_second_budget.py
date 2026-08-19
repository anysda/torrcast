"""Бюджет справки на пути второго захода: остаток цели или её собственный потолок."""

from __future__ import annotations

from torrcast.domain.facts.settings import FACTS_BUDGET
from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL, SECOND_LEAST
from torrcast.domain.picture import Picture
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient


def _second_budget(
    client: IndexerClient, name: str, found: list[Picture], progress: Progress
) -> float:
    """Сколько секунд отдаётся справке перед добором по второму имени картины.

    🔴 TC-386. **Отмены по бюджету у добора нет.** Остаток цели (:meth:`Prowlarr.spare`)
    задавал ему потолок, а ниже :data:`~torrcast.domain.goal_spare.SECOND_LEAST` отменял вовсе - и
    отмена стоила картины: при медленном первом круге (живой замер - Knaben 7.0 с вместо
    0.5) пул «тачек» падал с 28 раздач до 4-5, и поиск кончался отказом при живом
    каталоге. По лестнице целей «не включилось» сильнее «дольше 10 секунд», поэтому цель
    тут подчинена поиску: съеденный остаток не отменяет заход, а объявляется строкой.
    Остальные вторые заходы (уточнение, сезон, голос) бюджетом по-прежнему охраняются
    (:func:`_no_budget`) - у них есть честный отступ, тут его нет.
    """
    spare = client.spare()
    if spare >= SECOND_LEAST:
        # 🔴 TC-243. Картины не нашлось вовсе - без второго имени тут отказ, и справка
        # становится единственной опорой: ей отдаётся весь остаток цели за вычетом доли
        # круга, а не обычный потолок. Полутора секунд ей не хватает: прямая выборка
        # промолчала, а поиск Википедии и разбор описки - это ещё два-три запроса, и они
        # физически не успевают («Секреты Лос-Анджелеса» и «Реинкарнация (фильм, 2018)»
        # лежат первыми строками поиска, но приезжают уже никому не нужными).
        return spare - CIRCLE_SHARE if not found else min(FACTS_BUDGET, spare - CIRCLE_SHARE)
    # 🔴 TC-386. Остатка цели на добор не хватает - а добор всё равно делается. Отмена
    # тут стоила картины: на живом стенде «тачки» при медленном Knaben (7.0 с вместо
    # 0.5) теряли пул с 28 раздач до 4-5 и кончались отказом. По лестнице целей
    # «не включилось» сильнее «дольше 10 секунд», поэтому цель тут подчиняется:
    # справке - её обычный потолок, кругу добора - пол в целую цель
    # (:attr:`~torrcast.adapters.prowlarr.prowlarr.Prowlarr.cap_floor`), и человек читает про это
    # строку.
    progress.phase("")
    progress.note(
        f"поиск уже съел цель в {GOAL:.0f} с - добор по «{name}» всё равно делаю: "
        "картину ищут оба её имени"
    )
    return FACTS_BUDGET
