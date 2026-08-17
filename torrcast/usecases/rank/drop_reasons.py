"""Слова, которыми называется отсев раздачи до очереди; зовут счёт отсева и `cast log`."""

from __future__ import annotations

from typing import Final

#: Раздачи картины, отсеянные до очереди, по причинам (:func:`drop_reason`). Порядок
#: слов один на весь код: причина называется там, где считается, и печатается в
#: `cast log` теми же словами (:func:`torrcast.trace._event_line`).
OFF_SEASON: Final = "нужного сезона нет"
_NO_EPISODE: Final = "нужной серии нет по имени"
_DISC: Final = "образ диска"
_EXTRAS: Final = "дополнительные материалы, а не сама картина"
_HEAVY: Final = "тяжелее потолка"
_HEVC: Final = "hevc, а сплошного перекода нет"
_CODEC: Final = "кодек не тот"
_SMALL: Final = "кадр ниже 720p по имени"
_SOURCE: Final = "источник не HD"
_QUIET: Final = "имя молчит о качестве"
_PINNED: Final = "релиз назван руками"
