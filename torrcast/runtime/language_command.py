"""Собирает ответ на ``cast --ru`` / ``cast --en``: язык ложится в настройку, и о
переключении говорится вслух. Зовёт его слой команд (:mod:`torrcast.cli.language`)
через слот, который кладёт :func:`torrcast.runtime.configure_cli.configure_cli`.
"""

from __future__ import annotations

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.catalogs.tongue import _choose_tongue

#: Подтверждение печатается на том языке, на который переключились: "cast --en" не
#: вправе ответить по-русски. Строки продукта сегодня русские, и перевод их всех -
#: работа отдельная (TC-929, второй заход); тут называется только сам выбор.
#: Регистр названия языка не выравнивается между строками: у каждого языка свои
#: правила письма, а не образец соседа - в английском имя языка пишется с заглавной
#: буквы ("English"), в русском ("русский") строчной, и это не опечатка.
_ANNOUNCED = {"ru": "язык: русский", "en": "language: English"}


def language_command(language: str) -> int:
    """Записать язык в настройку и назвать выбранное вслух - на этом же языке."""
    config = load_config()
    config.language = language
    save_config(config)
    # Названная рядом работа идёт в ТОМ ЖЕ процессе (`cast --ru мумия`), и надписи в ней
    # обязаны быть уже новыми: следующего запуска, который перечитает настройку, тут нет.
    _choose_tongue(language)
    PrintConsole().write(_ANNOUNCED.get(language, f"язык: {language}"))
    return 0
