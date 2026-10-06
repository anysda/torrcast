"""Аргументы отбора карточки с закладкой: спросить ИМЕННО раздачу, что продолжит «Играть»."""

from __future__ import annotations

from torrcast.cli.parse_args import parse_args
from torrcast.domain.args import Args
from torrcast.domain.info_hash import info_hash
from torrcast.usecases.select.plan import Plan


def bookmark_args(plan: Plan, query: str, release: str, label: str) -> Args:
    """Аргументы отбора карточки: раздача ``release`` закреплена, если она есть в выдаче.

    Названную раздачу честностная проверка не подменяет (:meth:`torrcast.usecases.
    select_bench.bench.Bench._honest`): «релиз 9 на деле 648p - беру 1» забирал у карточки
    меню, хотя «Играть» продолжал раздачу закладки. Раздачи нет в выдаче - отбору
    остаётся предпочесть её имя (``card_release``).
    """
    args = parse_args([query, label] if label else [query])
    if release:
        number = next((at for at, one in enumerate(plan.ranked, 1) if info_hash(one) == release), 0)
        if number:
            args.release, args.release_hash = number, release
        else:
            args.card_release = release
    return args


__all__ = ["bookmark_args"]
