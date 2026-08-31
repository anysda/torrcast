"""Язык, на котором продукт говорит прямо сейчас.

Композиционный корень (:func:`torrcast.runtime.wire.wire`) кладёт сюда функцию выбора;
каталог надписей (:func:`torrcast.domain.catalogs.phrase.phrase`) спрашивает её заново.
Сам слой домена в файл не ходит, а без собранного внешнего мира говорит по-английски.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from torrcast.domain.torrcast_error import TorrcastError

#: Коды языка, которые продукт умеет говорить. Именем, а не голым литералом: голая
#: ``"ru"`` уже жила и тут, и в каталоге (:mod:`torrcast.domain.catalogs.phrase`)
#: порознь - опечатка в одном месте не билась бы со вторым, а тихо расходилась
#: (TC-929, просьба tc930).
RU: Final = "ru"
EN: Final = "en"


#: Умолчание совпадает с умолчанием настройки
#: (:attr:`torrcast.domain.config.Config.language`): английский - и язык, и запасной
#: каталог. Модуль, у которого корень не спросил ничего, говорит по-английски, а не
#: падает: язык - настройка показа, а не условие работы.
def _english() -> str:
    return EN


_TONGUE: Callable[[], str] = _english


def tongue() -> str:
    """Код языка, на котором собираются надписи."""
    return _TONGUE()


def _choose_tongue(language: str) -> None:
    """Назначить фиксированный язык надписей несобранному домену и его тестам.

    Живой процесс получает свежий держатель через :func:`_follow_tongue`.

    🔴 Опечатка в настройке (скажем, ``"de"``, вручную правленный файл) раньше тихо
    вырождалась бы в английский через запасной каталог (:func:`torrcast.domain.
    catalogs.phrase.phrase`) - неотличимо от честного ``cast --en``. Домен об этом
    молчать не вправе: он не пишет в файлы и не печатает, поэтому поднимает то же
    исключение, каким корень уже встречает битый конфиг
    (:func:`torrcast.adapters.filesystem.state.load_config.load_config`), - а не
    придумывает молчаливый третий язык.
    """
    global _TONGUE
    if language not in (RU, EN):
        # 🔴 Спросить каталог, на каком языке пожаловаться, тут нечем: каталог и есть
        # тот, у кого спрашивают язык, и вопрос ходит по кругу. Домен в файлы не ходит
        # и не печатает (см. докстроку модуля) - значит и второй договор не завести.
        # Берётся уже выбранный: нечитаемая настройка говорит по-английски
        # (:func:`torrcast.adapters.filesystem.state.chosen_language.chosen_language`,
        # тот же выбор в TC-947) - и этот текст с ней согласован, а не переведён на
        # русский. Явное следствие: человек с опечаткой в файле настройки, будь его
        # язык хоть русским, читает жалобу по-английски.
        raise TorrcastError(
            f"unknown setting language {language!r}: the only ones spoken are {RU!r} and {EN!r}"
        )

    def fixed() -> str:
        return language

    _TONGUE = fixed


def _follow_tongue(chosen: Callable[[], str]) -> None:
    """Брать язык из одного свежего держателя при каждой надписи."""
    global _TONGUE
    # Проверить договор поставщика до установки, не превращая его первое значение в
    # снимок: дальше ``tongue`` продолжит звать саму функцию.
    _choose_tongue(chosen())
    _TONGUE = chosen
