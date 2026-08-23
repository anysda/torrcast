"""Самый тяжёлый сосед по группе, которого сместит потолок; зовёт порядок меню."""

from __future__ import annotations

from torrcast.domain.release import Release
from torrcast.usecases.rank.bitrate_of import bitrate_of

Key = tuple[object, ...]


def heavy_peers(
    releases: list[Release], keys: dict[int, Key], runtime: float, recode_at: float
) -> dict[Key, float]:
    """Битрейт самой тяжёлой раздачи группы из тех, кого ступень потолка сместит вниз.

    Группа тут - равные по всем ступеням ВЫШЕ потолка приёмника, то есть ровно те, кого
    :func:`fits_receiver` и разводит между собой; ``keys`` отдаёт ключ группы по ``id``
    раздачи, как его считает :func:`rank_releases`. Тот же приём, что у живости кадра:
    ступени нужно число по группе, а группу знает только порядок меню.

    Считаются раздачи ТЯЖЕЛЕЕ потолка, и только они: лёгкую ступень не смещает, менять
    её не на что, и знаменателя у размена там нет. Группа без единой тяжёлой раздачи
    получает ноль, и пол размена (:data:`~torrcast.domain.rank_settings.TRADE_FLOOR`) в
    ней не действует вовсе - ступень там плоская, порядок решают сиды.

    Знаменатель берётся по группе, а не по всему пулу, и цена выбора замерена: по пулу
    та же доля отнимает предпочтение у 534 раздач корпуса вместо 13. Один тяжёлый 4К в
    выдаче поднимал бы пол сразу всем раздачам картины, включая те, которым он не
    соперник ни на одной ступени.
    """
    heavy: dict[Key, float] = {}
    for release in releases:
        mbit = bitrate_of(release, runtime)
        if mbit is not None and mbit > recode_at:
            key = keys[id(release)]
            heavy[key] = max(heavy.get(key, 0.0), mbit)
    return heavy
