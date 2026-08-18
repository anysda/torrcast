"""Прежний адрес «ч:мм:сс» отдаёт ровно ту же единицу, что и предметная область."""

from __future__ import annotations

from torrcast.domain._hms import _hms as home
from torrcast.usecases.rank._hms import _hms


def test_the_old_address_names_the_same_unit() -> None:
    assert _hms is home
