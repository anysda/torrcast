"""Место записи, чья раздача не играется: закладка обязана пережить смену релиза."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def _kept_dead(state: WatchState, key: str, args: Args) -> Entry | None:
    """Сохранённое место похороненной раздачи; ``None`` - держать нечего или нельзя.

    Закладка - ценность, и умирает не она, а релиз. Запись про релиз (магнит, файл,
    дорожка) меняется целиком, запись про МЕСТО остаётся: позиция доезжает до записи
    нового показа (:func:`torrcast.usecases.cast_command._cmd_play._cmd_play`), а память
    озвучки и студии переживает смену релиза сама - на том она и заведена
    (:attr:`torrcast.domain._playing._Playing.voice`).

    🔴 У сериала место - это пара «серия и позиция», и одной позицией оно не переносится:
    новый релиз может начинаться с другой серии, и тогда сохранённая секунда указывала бы
    внутрь чужой серии. Серию в запрос ставит :func:`_kept_place` - тем же приёмом, что и
    при названном руками релизе (TC-807), - и место оттуда приезжает вместе с ней. Здесь
    остаётся фильм: у него одно место на всю картину, и переносить его безопасно.

    Спрашивается запись по ключу КАРТИНЫ, а не по тексту запроса: закладка, ответившая
    после меню (:func:`_continue_picked`), до найденной по запросу записи не доходит
    вовсе, а место терять нельзя и там.
    """
    buried = state.get(key)
    if buried is None or buried.serial or not args.buried(buried.magnet):
        return None
    return buried
