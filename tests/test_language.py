"""Сторож: смена настройки под ЖИВЫМ держателем языка меняет следующий ответ.

Бот - долгоживущий процесс, и `cast --ru` / `cast --en` обязан действовать без
рестарта юнита. Держатель языка один на консоль и бота
(:mod:`torrcast.domain.catalogs.tongue`), поэтому мера ставится на саму связь:
настройку переписывают так, как это делает соседний процесс, - а ответ спрашивается
у слоя строк бота и у каталога домена разом.
"""

from __future__ import annotations

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian
from tgbot.i18n import i18n
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.runtime.en import en as runtime_en
from torrcast.domain.catalogs.runtime.ru import ru as runtime_ru
from torrcast.domain.catalogs.tongue import tongue
from torrcast.domain.config import Config
from torrcast.runtime.language_command import language_command
from torrcast.runtime.wire import wire


def test_a_setting_changed_under_a_live_holder_moves_the_next_reply() -> None:
    """Переписанная снаружи настройка видна со СЛЕДУЮЩЕЙ надписи, без рестарта."""
    save_config(Config(tv="10.0.0.50", language="en"))
    wire()
    assert (i18n("busy"), tongue()) == (english()["busy"], "en")

    save_config(Config(tv="10.0.0.50", language="ru"))

    assert (i18n("busy"), tongue()) == (russian()["busy"], "ru")


def test_a_chat_switch_does_not_freeze_the_holder_against_an_external_one() -> None:
    """🔴 Чатный `cast --ru` не вправе запереть держатель: за ним придёт консольный.

    Команда языка исполняется В процессе бота: чатный `cast --ru` - это тот же
    :func:`torrcast.runtime.language_command.language_command`. Заморозь она держатель
    снимком - и внешний `cast --en` до бота бы не дошёл: при английской настройке чат
    продолжил бы читать надписи домена по-русски, двумя языками разом.
    """
    save_config(Config(tv="10.0.0.50", language="en"))
    wire()
    assert language_command("ru") == 0
    assert i18n("busy") == russian()["busy"]
    assert phrase("runtime.announced_language", name="русский") == runtime_ru()[
        "runtime.announced_language"
    ].format(name="русский")

    # Так выглядит консольный `cast --en` соседнего процесса: та же настройка, тот же файл.
    save_config(Config(tv="10.0.0.50", language="en"))

    assert (i18n("busy"), tongue()) == (english()["busy"], "en")
    assert phrase("runtime.announced_language", name="English") == runtime_en()[
        "runtime.announced_language"
    ].format(name="English")
