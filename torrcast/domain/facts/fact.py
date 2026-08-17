"""Справка по одной картине; её собирает сценарий меню и хранит кэш."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Fact:
    """Справка по одной картине. Пустые поля — норма: нет данных, значит нет строки."""

    about: str = ""
    #: Уже с источником: «IMDb 7.6». Голая цифра в меню не значила бы ничего.
    rating: str = ""
    #: Готовая строка «1 ч 47 мин» - не минуты: считать их в уме человек не обязан.
    runtime: str = ""

    def __bool__(self) -> bool:
        return bool(self.about or self.rating or self.runtime)
