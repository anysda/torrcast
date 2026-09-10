"""Виноватый недосмотренного показа: назвать его вслух и верно, на похоронах сеанса.

Зовёт это конец показа (:mod:`torrcast.usecases.playback._show_end`) - отсюда и живёт
рядом, а не среди гашения хозяйства: строка поиска виноватого своя, и модуль держит её
в пределах потолка длины.
"""

from __future__ import annotations

from typing import NoReturn

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.start_refusal import RECEIVER_DID_NOT_ANSWER, SOURCE_COULD_NOT_BE_READ
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal
from torrcast.ports.refusal_record import refusal_record
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.source_blame import _blamed


def _blame_the_end(
    supply: StreamSource | None, shown: bool = True, clock: Clock | None = None
) -> NoReturn:
    """Показ кончился недосмотренным - назвать виноватого, и назвать верно. Всегда бросает.

    🔴 Последняя строка показа - последняя возможность сказать правду. Раньше показ
    кончался обвинением «приёмник не досмотрел поток» при живом приёмнике и мёртвой
    службе раздач. Замерено на стенде: перезапуск службы под показом давал ровно эту
    строку, и про источник в ней не было ни слова.

    ``shown`` - видел ли зритель хоть один кадр. Разница не косметическая: «не досмотрел»
    и «не увидел вовсе» - это две разные аварии для того, кто сидит перед экраном, и
    вторая стоит выше на лестнице цели. Сюда она доходит только исчерпав лестницу
    воскрешения: показ, не давший кадра, сперва поднимают, и лишь потом хоронят.

    Спросить источник тут можно спокойно: показ уже кончился, горячего пути нет, а
    человеку и следу уходит одна и та же причина.

    🔴 Здоровая подача - отдельная правда (:func:`_swarm_cleared`): назвать вместо роя
    приёмник было бы той же подменой с другим именем.
    """
    why_source = _blamed(supply, clock if clock is not None else _state.CLOCK)
    if why_source and not _swarm_cleared(supply):
        journal().offline(why=why_source, asked=True)
        if not shown:
            # Причину знает это место и только оно: мосту смерть юнита видна голым
            # классом. Слово пишется файлом - экрану подготовки, который ждёт этот
            # подъём (:mod:`torrcast.domain.start_refusal`).
            refusal_record().record(SOURCE_COULD_NOT_BE_READ)
            raise InfraError(phrase("playback.no_picture_source_unreadable", why=why_source))
        raise InfraError(phrase("playback.source_unreadable_cut_short", why=why_source))
    if not shown:
        if supply is not None and supply.kept_up:
            # Рой держался, а кадра не было: виноватого продукт не различает, и слово
            # тут не пишется - экран откажет короткой строкой без выдуманного хвоста.
            raise InfraError(phrase("playback.no_picture_supply_held"))
        refusal_record().record(RECEIVER_DID_NOT_ANSWER)
        raise InfraError(phrase("playback.no_picture_receiver_refused"))
    raise InfraError(phrase("playback.receiver_did_not_finish"))


def _swarm_cleared(supply: StreamSource | None) -> bool:
    """Снимает ли окно наблюдений сеанса жалобу на просевший рой.

    🔴 Правило живёт ровно ЗДЕСЬ, на похоронах, и нигде больше. Скорость службы - величина
    нашего же спроса: пока упаковка тянет байты, короткий замер говорит о рое, а после
    того как показ сдался, тянуть перестали, и тот же замер не говорит уже ни о чём.
    Замер 03-09-2026 на стенде `.136`: весь сеанс след писал долю 2.99-3.61, а человеку
    показ назвал посмертные 0.20 Мбит/с и обвинил здоровую раздачу.

    ⚠️ Тем же окном НЕЛЬЗЯ править живой ответ источника: там непустая жалоба - это не
    строка, а действие, и просадка посреди показа переводит упаковку в ожидание
    (:func:`torrcast.usecases.revive_playback._endure._endure`). Снятая на живом пути, она
    превращает переживаемый обрыв в смерть показа - замерено на этой же улике.

    Прочие беды источника окно не трогает: служба, легшая насмерть, и раздача без трекеров
    лежат одинаково и на живом показе, и на мёртвом, нашим спросом их не измерить.
    """
    return supply is not None and supply.thin and supply.kept_up
