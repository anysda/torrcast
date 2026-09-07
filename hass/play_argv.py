"""Собрать ``argv`` показа для :meth:`hass.bridge.Bridge.play`.

Молчат все четыре новых довода - и ``argv`` выходит ровно таким же, как до них: старый
вызов Home Assistant не видит разницы. Серия едет тем же токеном ``sNeM``, каким её
понял бы человек в строке запроса
(:func:`torrcast.domain.parse_episode.parse_episode`), а не новым флагом - CLI умеет
её уже сегодня.
"""

from __future__ import annotations

from torrcast.cli.parse_args import FROM_START_FLAG


def play_argv(
    query: str,
    pick: int | None,
    voice: str | None,
    season: int | None,
    episode: int | None,
    from_start: bool,
) -> list[str]:
    """``argv``, каким CLI уже читает ``--pick``, серию, ``--voice`` и ``--new``."""
    # 🔴 Серия идёт СРАЗУ за запросом, до любого флага, и это не про красоту. Запрос у
    # CLI - позиционный довод из многих слов (``nargs="*"``); argparse забирает их до
    # первого флага, а всё позиционное ПОСЛЕ него объявляет лишним: `--pick 2 s1e2` даёт
    # `unrecognized arguments: s1e2` и обрывает показ серии с выбранной раздачей.
    args = [query]
    if season is not None and episode is not None:
        args.append(f"s{season}e{episode}")
    if pick is not None:
        args += ["--pick", str(pick)]
    if voice:
        args += ["--voice", str(voice)]
    if from_start:
        args.append(FROM_START_FLAG)
    return args
