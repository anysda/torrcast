"""Ключ раздачи карточки и пропажа раздачи закладки из выдачи (TC-1263: закладка главнее)."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.card_release import card_release
from web.heard import Heard


def release_keys(
    plan: Plan, episodes: Release | None, heard: Heard | None, live: bool
) -> dict[str, JsonValue]:
    """Ключ раздачи и «раздачи закладки нет в выдаче» (:func:`web.card_seasons.card_seasons`).

    Пропажа говорится только по живому кругу: в записи с диска «Рика и Морти» не было строк
    JacRed, и раздача закладки ec1be32a «пропадала», хотя живой пул её держал. Показ, не
    найдя её в выдаче, сыграет другую раздачу и запишет закладку на неё.
    """
    gone = live and episodes is not None and episodes not in plan.picture.releases
    return {"release": card_release(episodes, heard), "bookmark_gone": gone}


__all__ = ["release_keys"]
