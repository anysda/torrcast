"""Что страница нашла до «Играть»: круг карточки и её картина по ключу.

У консольного ``cast`` карточки нет: его круг свой, а картина по ключу ищется точным
совпадением. Мост со страницей кладёт сюда свои (:func:`_configure_play_stage`), и показ
с карточки берёт тот же круг, что карточка уже спросила, а не заводит второй.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from torrcast.usecases.discover.search_circle import search_circle

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def _exact_picture(plans: list[Plan], key: str) -> int:
    """Номер картины с этим ключом в круге; нет такой - ноль."""
    return next((n for n, plan in enumerate(plans, start=1) if plan.picture.key == key), 0)


@dataclass(frozen=True)
class PlayStage:
    """Круг показа и правило «картина по ключу карточки»."""

    circle: Callable[..., list[Plan]] = search_circle
    picture: Callable[[list[Plan], str], int] = _exact_picture


_stage = PlayStage()


def _play_stage() -> PlayStage:
    """То, что назначил корень; до его слова - круг и ключ консольного ``cast``."""
    return _stage


def _configure_play_stage(stage: PlayStage) -> None:
    """Назначить показу круг и ключ карточки. Зовёт мост страницы и тесты."""
    global _stage
    _stage = stage
