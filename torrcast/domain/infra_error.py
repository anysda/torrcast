"""Ошибка InfraError; используется публичным API."""

from torrcast.domain.torrcast_error import TorrcastError


class InfraError(TorrcastError):
    """Легла инфраструктура: Prowlarr / TorrServer / приёмник. Код выхода 2."""
