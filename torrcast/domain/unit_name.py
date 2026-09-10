"""Имя transient-юнита показа ЭТОГО экземпляра.

До TC-1137 имя было одно на весь узел, и все экземпляры стенда били в один юнит
``torrcast-play``: запуск показа в одном гасил идущий показ другого. Боевой экземпляр
на узле один и держит прежнее имя; прочие получают метку своего состояния
(:func:`torrcast.domain.instance_slug.instance_slug`).
"""

from __future__ import annotations

from torrcast.domain.instance_slug import instance_slug
from torrcast.domain.unit_naming import _UNIT_NAME


def unit_name() -> str:
    """Имя юнита показа: базовое у боевого экземпляра, с меткой состояния у прочих."""
    slug = instance_slug()
    return f"{_UNIT_NAME}-{slug}" if slug else _UNIT_NAME
