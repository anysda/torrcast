"""Начатый сериал, выбранный дверью меню: продолжить с места закладки, как без ручек.

Зовёт его закладка выбранной картины (:func:`torrcast.usecases.cast_command._bookmark.
_continue_picked`), когда картина уже названа.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.config import Config
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._account_watched import _account_watched
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.start_clock import _Clock

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def _picked_serial(
    config: Config,
    state: WatchState,
    key: str,
    title: str,
    bench: Bench,
    *,
    args: Args,
    clock: _Clock,
) -> int | None:
    """Серия и позиция закладки - тот же ответ, что даёт ``cast <сериал>`` без ручек.

    🔴 Кнопка «Играть» веба входит в продукт дверью меню (``--pick N``), и начатый сериал
    уходил отсюда обычным путём с первой серии: стартовая запись показа ложилась под тот
    же ключ картины и стирала место, после чего и бот играл s1e1 с нуля (прод 11-09-2026:
    s3e14 с 0:09:06 стало s1e1). Теперь путь тот же, что у запроса без ручек
    (:func:`torrcast.usecases.cast_command._cmd_play._cmd_play`): досмотренная серия
    списывается (:func:`_account_watched`), и показ идёт записанной раздачей с места.

    Записанная раздача не играется (:func:`_continue` её хоронит) - серия закладки встаёт
    в запрос, и обычный путь берёт ту же серию у другой раздачи, а позиция доезжает по
    ключу картины (:func:`torrcast.usecases.cast_command._kept_dead._kept_dead`). Меняется
    тот самый ``args``, которым дальше идёт выбор: картина названа, и запрос после этой
    точки читают только отбор серии и подпись показа.
    """
    saved = state.get(key)
    if saved is None:
        return None
    # Бухгалтерия пишет в состояние - ей даётся сама запись, а не копия с именем для экрана.
    entry = _account_watched(state, (key, saved))[0][1]
    bench.drop_all()
    code = _continue(config, key, replace(entry, title=title), args=args, clock=clock)
    if code is None and args.buried(entry.magnet) and entry.label and not entry.done:
        args.query.append(entry.label)
    return code
