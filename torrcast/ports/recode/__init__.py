"""Порт медиатракта: решение о перекоде и кодировщик тяжёлых кусков.

Дом у этих имён один на весь проект, и это не вкусовщина. Договор адаптера структурный:
два пакета, назвавшие его каждый у себя, совпадут только формой, а формы у них разные -
показ спрашивает у кодировщика одно, лента другое, прогрев третье. Пока имя жило по копии
на пакет, объект показа не подходил ни ленте, ни прогреву, хотя это один и тот же объект.
Здесь широкий договор назван один раз, а узкие доли отрезаны от него наследованием.
"""

from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.encoding_key import EncodingKey
from torrcast.ports.recode.encoding_rate import EncodingRate
from torrcast.ports.recode.feed_recoder import FeedRecoder
from torrcast.ports.recode.recode_pace import RecodePace
from torrcast.ports.recode.recode_rival import RecodeRival
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.ports.recode.spot_rival import SpotRival

__all__ = [
    "Encoding",
    "EncodingKey",
    "EncodingRate",
    "FeedRecoder",
    "RecodePace",
    "RecodeRival",
    "SpotRecoder",
    "SpotRival",
]
