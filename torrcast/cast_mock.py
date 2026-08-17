"""Совместимый фасад сухого приёмника.

Сам приёмник живёт в :mod:`torrcast.adapters.chromecast.mock.mock_receiver`, цифры
приёмки - в :mod:`torrcast.domain.reception_report`. Отсюда их берут прежние импорты.
"""

from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver as MockReceiver
from torrcast.domain.reception_report import ReceptionReport as Report

__all__ = [
    "MockReceiver",
    "Report",
]
