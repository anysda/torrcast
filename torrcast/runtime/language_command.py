"""Собирает ответ на ``cast --ru`` / ``cast --en``: язык ложится в настройку, и о
переключении говорится вслух. Зовёт его слой команд (:mod:`torrcast.cli.language`)
через слот, который кладёт :func:`torrcast.runtime.configure_cli.configure_cli`.
"""

from __future__ import annotations

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import EN, RU

#: Имя языка внутри подтверждения - не надпись продукта, а название САМОГО языка, и
#: оно пишется его собственным письмом всегда, независимо от того, на какой каталог
#: попадёт `phrase()`: в английском имя языка с заглавной буквы ("English"), в русском
#: ("русский") строчной, и это не опечатка, а разное письмо для разных языков.
_LANGUAGE_NAMES = {RU: "русский", EN: "English"}


def language_command(language: str) -> int:
    """Записать язык в настройку и назвать выбранное вслух - на этом же языке."""
    config = load_config()
    config.language = language
    save_config(config)
    # Названная рядом работа идёт в ТОМ ЖЕ процессе (`cast --ru мумия`), и надписи в ней
    # обязаны быть уже новыми: следующего запуска, который перечитает настройку, тут нет.
    # Дернать держатель НАСИЛЬНО не нужно и вредно: собранный корнем процесс держит
    # ЖИВОГО читателя настройки (:func:`torrcast.domain.catalogs.tongue._follow_tongue`),
    # и свежая запись видна ему со следующей же надписи сама. Замороженный же снимок
    # (:func:`~torrcast.domain.catalogs.tongue._choose_tongue`) отрезал бы долгоживущего
    # бота от смены языка снаружи: чатный `cast --ru` запирал бы надписи домена на
    # русском, и после консольного `cast --en` человек читал бы чат на двух языках разом.
    name = _LANGUAGE_NAMES.get(language, language)
    PrintConsole().write(phrase("runtime.announced_language", name=name))
    return 0
