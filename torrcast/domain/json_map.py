"""Объект разобранного JSON: что угодно - в словарь, чужое - в пустой."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue


def json_map(value: JsonValue) -> dict[str, JsonValue]:
    """Объект JSON как словарь; ``None`` и не-объект читаются как пустой объект.

    Так разбор и читал их всегда: ``payload.get("query", {}) if isinstance(payload, dict)``
    и ``rec.get("got") or {}`` - это одно и то же правило, написанное дважды. Пустой
    словарь тут не заглушка ошибки, а ответ «такого поля в ответе нет», и отличать его от
    «поле есть, но пустое» разбору не нужно: оба означают, что читать нечего.
    """
    return value if isinstance(value, dict) else {}
