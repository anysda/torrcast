"""Сборка модели из разобранного JSON: знакомые ключи в поля, чужие - за борт."""

from __future__ import annotations

from collections.abc import Callable, Container, Mapping
from typing import TypeVar

from torrcast.domain.json_value import JsonValue

T = TypeVar("T")


def json_model(model: Callable[..., T], data: Mapping[str, JsonValue], known: Container[str]) -> T:
    """Собрать модель из словаря JSON, молча потеряв ключи, которых у неё нет.

    Так читаются оба наших файла - настройки и состояние. Незнакомый ключ не ошибка, а
    обычное дело: файл переживает смену версии, и запись, сделанную новее нас, читать
    надо ровно тем, что мы понимаем.

    ⚠️ Значения при этом НЕ проверяются и не приводились никогда: что человек записал в
    файл, то в поле и приедет. Разбор тут собирает модель, а не судит её содержимое.
    """
    return model(**{key: value for key, value in data.items() if key in known})
