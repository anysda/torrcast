"""Слова, которыми называется отсев раздачи до очереди; зовут счёт отсева и `cast log`."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase

#: Причина называется там, где считается, и печатается в `cast log` теми же словами
#: (:func:`torrcast.domain.digest._event_line`). Функции, а не константы: слово обязано
#: отвечать текущему языку показа (:func:`~torrcast.domain.catalogs.tongue.tongue`), а не тому,
#: что был выбран при импорте модуля.


def off_season() -> str:
    """Причина отсева: у сериала в выдаче нет раздач нужного сезона."""
    return phrase("rank.reason_off_season")


def _no_episode() -> str:
    return phrase("rank.reason_no_episode")


def _disc() -> str:
    return phrase("rank.reason_disc")


def _extras() -> str:
    return phrase("rank.reason_extras")


def _heavy() -> str:
    return phrase("rank.reason_heavy")


def _hevc() -> str:
    return phrase("rank.reason_hevc")


def _codec() -> str:
    return phrase("rank.reason_codec")


def _small() -> str:
    return phrase("rank.reason_small")


def _source() -> str:
    return phrase("rank.reason_source")


def _quiet() -> str:
    return phrase("rank.reason_quiet")


def _pinned() -> str:
    return phrase("rank.reason_pinned")
