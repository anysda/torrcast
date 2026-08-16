"""Ошибка SwarmError; используется публичным API."""

from torrcast.domain.infra_error import InfraError


class SwarmError(InfraError):
    """Раздача не ответила: о её содержимом ничего не известно."""
