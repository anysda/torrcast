"""Картина, за которой идут: самая полная из найденных; на неё смотрит гейт добора."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def _leading(pictures: list[Picture]) -> Picture | None:
    """Картина, за которой идут: самая полная из найденных.

    Именно она - дефолт меню и она же играет, когда терминала нет. Гейт добора смотрит на
    неё, а не на список целиком: список одноимённых картин от добора и должен пополняться,
    а вот вожак меняться не должен.
    """
    return max(pictures, key=lambda p: len(p.releases), default=None)
