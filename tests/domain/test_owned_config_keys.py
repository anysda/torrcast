"""Зеркало :mod:`torrcast.domain.owned_config_keys`: чем в файле настроек владеет человек.

Сторожатся два свойства, ради которых список и заведён: он состоит из настоящих полей
настроек, а не из опечаток, и установщик несёт РОВНО тот же список. Разъехаться им
нечем - install.sh на питон не смотрит, а питон на shell, - поэтому держит их мера.
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from tgbot.config import Config as BotConfig
from torrcast.domain.config import Config
from torrcast.domain.owned_config_keys import OWNED_BY_HUMAN

REPO = Path(__file__).parents[2]
SCRIPT = (REPO / "install.sh").read_text(encoding="utf-8")


def _config_kept() -> frozenset[str]:
    """Белый список установщика - как он написан в самом install.sh."""
    found = re.search(r"^CONFIG_KEPT='([^']*)'$", SCRIPT, re.M)
    assert found is not None, "install.sh больше не объявляет CONFIG_KEPT одной строкой"
    return frozenset(found.group(1).split())


def test_every_owned_name_is_a_setting_that_really_exists() -> None:
    """Имя из списка обязано быть настоящим полем, а не опечаткой.

    Опечатка тут не краснеет сама: ``jq`` молча не найдёт такого ключа, а запись
    настроек молча его не напишет - и названная человеком настройка уедет в умолчание
    кода при следующей же установке.
    """
    assert OWNED_BY_HUMAN - set(Config.__dataclass_fields__) == set()
    assert _config_kept() - (set(Config.__dataclass_fields__) | _telegram()) == set()


def test_the_installer_carries_over_exactly_what_the_code_calls_the_humans() -> None:
    """Белый список установщика и белый список кода - один список, а не два.

    Разойдутся - и поднятое умолчание снова начнёт переживать установку, ровно как
    ``warm_budget_gb`` переживал её на чёрном списке (TC-549).

    Языка в списке установщика нет НАРОЧНО, хотя владеет им тоже человек: его переносит
    ``$LANGUAGE``, прочитанный из живого конфига ещё до поднятия прав. Перенеси его ещё
    и белым списком - и ключ ``-ru`` при повторной установке молча отменялся бы прежним
    значением. Три ключа бота, наоборот, есть только у установщика: у :class:`Config`
    продукта таких полей нет вовсе, их список - поля :class:`tgbot.config.Config`.
    """
    assert _config_kept() == (OWNED_BY_HUMAN - {"language"}) | _telegram()


def _telegram() -> set[str]:
    """Ключи телеграм-бота, живущие в том же файле настроек."""
    return {item.name for item in fields(BotConfig)}
