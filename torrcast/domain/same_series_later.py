"""Картина позднего года - продолжение сериала, а не ремейк того же имени."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.domain.picture import Picture


def same_series_later(later: Picture, year: int | None, season: int) -> bool:
    """Поздняя картина сериала продолжает счёт сезонов ранней, а не начинает свой.

    Год позже бывает у позднего сезона («Мажор» 2014, пятый сезон подписан 2026) и у
    ремейка («Доктор Кто» 1963 и 2005). Имя и даже оригинал у ремейка те же, поэтому
    решает счёт: просят не первый сезон, и первого среди раздач поздней картины нет.
    Тот же год - одна картина, разбитая кругом; год раньше - не продолжение.
    """
    if not year or not later.year or later.year == year:
        return True
    return (
        later.year > year
        and season > 1
        and not any(1 in (release.seasons or (release.season,)) for release in later.releases)
    )


__all__ = ["same_series_later"]
