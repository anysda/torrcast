"""Нога хоста: имя интерфейса, наш адрес на нём и маска.

Собирает их опрос интерфейсов, разбирает их отбор подсетей к обходу."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Net:
    """Нога хоста: имя интерфейса, наш адрес на нём и маска."""

    name: str
    address: str
    mask: str
