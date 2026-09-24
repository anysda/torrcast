"""Отказ: полный многосезонный пак доказал конец нужного сезона."""

from __future__ import annotations

from torrcast.domain.not_found_error import NotFoundError


class EpisodeAbsentError(NotFoundError):
    """Нужный номер лежит за последней серией сезона полного пака."""

    def __init__(self, message: str, season: int, last: int) -> None:
        super().__init__(message)
        self.season = season
        self.last = last


__all__ = ["EpisodeAbsentError"]
