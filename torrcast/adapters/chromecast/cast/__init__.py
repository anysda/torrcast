"""Живой приёмник Chromecast и выбор приёмника; фасад имён обоих приёмников.

⚠️ Повадки конкретных приёмников тут ЕСТЬ, и утверждать обратное (прежняя строка гласила
«Samsung-специфики здесь нет и быть не должно») - врать: в пакете живёт сторож подвиса
с порогами, снятыми с Samsung Q70D (:func:`_nudge`). Правило другое и выполнимое: ни одно
из этих чисел не прибито здесь константой - все они приходят из профиля приёмника
(:mod:`torrcast.profile`), а константы :class:`_Settings` остаются умолчанием
осторожного профиля.

Класс приёмника разложен слоями: :class:`_Settings` несёт пороги, :class:`_State` - поля
сессии, :class:`_Talk` - весь разговор с pychromecast (соединение, статус, LOAD, чистое
приложение), а сам :class:`ChromecastReceiver` - занятия показа, каждое своим файлом.
Подмену на стенде ставят именно на :class:`_Talk`, поэтому эти четыре ручки и стоят
одним слоем.

Сухой приёмник живёт в :mod:`torrcast.adapters.chromecast.mock.mock_receiver`, договор
приёмника - в :mod:`torrcast.ports.receiver`; оба реэкспортируются отсюда, потому что
звать их привычно именно из ``torrcast.cast``.
"""

from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver
from torrcast.adapters.chromecast.cast.hls_hints import HLS_HINTS, HLS_TYPE
from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise
from torrcast.adapters.chromecast.cast.make_receiver import make_receiver
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.position import Position
from torrcast.domain.reception_report import ReceptionReport as Report
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.trust_anchor import trust_anchor
from torrcast.ports.receiver import Receiver

#: Статический список нужен mypy для реэкспортов: :mod:`torrcast.cast` остаётся тем
#: именем, из которого приёмники зовут и показ, и тесты.
__all__ = [
    "HLS_HINTS",
    "HLS_TYPE",
    "NOT_RAISED",
    "ChromecastReceiver",
    "MockReceiver",
    "Position",
    "Receiver",
    "Report",
    "StartRefusedError",
    "hush_cosmetic_noise",
    "make_receiver",
    "trust_anchor",
]
