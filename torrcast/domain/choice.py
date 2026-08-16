"""Результат выбора профиля телевизора и объяснение выбора."""

from dataclasses import dataclass

from torrcast.domain.profile import Profile

__all__ = ["Choice"]


@dataclass(frozen=True, slots=True)
class Choice:
    """Выбранный профиль приёмника и источник решения."""

    profile: Profile
    how: str
