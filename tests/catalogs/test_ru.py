"""Парность каталогов Telegram: текст следует за языком продукта через слой фраз."""

from __future__ import annotations

import re

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian
from tgbot.i18n import i18n
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue

#: Именованные подстановки надписи: у пары каталогов они обязаны совпадать поимённо,
#: иначе русская строка соберётся с дыркой либо упадёт о неизвестное имя.
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_russian_translates_every_english_key() -> None:
    assert russian().keys() == english().keys()


def test_placeholders_match_between_catalogs() -> None:
    for key in english():
        assert set(_PLACEHOLDER.findall(english()[key])) == set(
            _PLACEHOLDER.findall(russian()[key])
        ), key


def test_every_key_is_spoken_through_the_layer_on_both_languages() -> None:
    """🔴 Сторож связи «текст следует за языком продукта», а не снимок литералов.

    Каждый ключ спрашивается у самого слоя (:func:`tgbot.i18n.i18n`) при обоих языках
    держателя, и ответ обязан совпасть с каталогом ЭТОГО языка: отвечи слой снимком,
    взятым при старте, или чужим каталогом - половина пробега покраснеет. Литералы сюда
    не вписаны: строки живут в каталогах и правятся там, не трогая сторожа.
    """
    for key, template in english().items():
        values = dict.fromkeys(_PLACEHOLDER.findall(template), "значение")
        _choose_tongue(EN)
        assert i18n(key, **values) == template.format(**values), key
        _choose_tongue(RU)
        assert i18n(key, **values) == russian()[key].format(**values), key
