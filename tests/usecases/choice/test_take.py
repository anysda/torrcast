"""Зеркало :mod:`torrcast.usecases.choice.take`: приговор ступени взятия.

Мерится тут ровно одно свойство записи, и оно же - лечение TC-829: номер в приговоре
ОДИН. Пока номеров было бы два - «кого греть» и «кого взять», - их снова заполняли бы
разные ветки, и шов вернулся бы под другим именем.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from torrcast.usecases.choice.take import Take


def test_the_take_carries_exactly_one_number() -> None:
    """🔴 Номер в приговоре один: разойтись прогреву со взятием физически нечем.

    Заведи второе числовое поле - и оно станет вторым мнением: одно заполнит страж,
    другое дефолт, и на корпусе снова разъедется то, что разъезжалось на десяти
    запросах из семидесяти четырёх. Поэтому число полей тут - утверждение, а не описание.
    """
    numbered = [one.name for one in fields(Take) if "int" in str(one.type)]

    assert numbered == ["number"], "у приговора обязан быть ровно один номер"


def test_the_take_is_frozen_so_no_one_rewrites_the_number_on_the_way() -> None:
    """Приговор неизменяем: между прогревом и вопросом номер переписать некому."""
    verdict = Take(1)

    with pytest.raises(FrozenInstanceError):
        verdict.number = 2  # type: ignore[misc]
    assert verdict.number == 1
