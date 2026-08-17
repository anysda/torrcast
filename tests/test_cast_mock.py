"""Зеркало :mod:`torrcast.cast_mock`."""

from __future__ import annotations

import torrcast.cast_mock as facade
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.reception_report import ReceptionReport


def test_the_facade_hands_out_the_very_same_units() -> None:
    """Прежние импорты доезжают до тех же единиц, а не до их копий."""
    assert facade.MockReceiver is MockReceiver
    assert facade.Report is ReceptionReport
    assert sorted(facade.__all__) == ["MockReceiver", "Report"]


def test_the_show_takes_its_receiver_through_the_facade() -> None:
    """Показ берёт сухой приёмник прежним именем - и получает работающий приёмник."""
    from torrcast import cast

    assert cast.MockReceiver is MockReceiver
    assert cast.Report is ReceptionReport
    assert not cast.Report().ok, "приёмник вообще ничего не видел"
