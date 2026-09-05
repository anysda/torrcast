"""Зеркало :mod:`torrcast.usecases.warm.key_form`: отпечаток формы ключа прогретого."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

import torrcast.usecases.warm.key_form as key_form
from torrcast.usecases.warm.warm_key import warm_key

if TYPE_CHECKING:
    import pytest


def test_the_stamp_moves_with_the_key_it_is_taken_from(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отпечаток формы считается тем же ``warm_key``, которым живёт продукт.

    Иначе сироты прежней формы не узнаются никем и место остаётся занятым навсегда. Проба
    двигает ровно ту половину ключа, которой на копийном показе нет вовсе: отпечаток,
    снятый с одного копийного ключа, такой правки не заметил бы, а полки после неё уже
    сироты. Отпечаток, записанный числом руками, не заметил бы её тем более.
    """
    before = key_form._stamp()

    def _changed_on_the_recode_path(*args: Any, **rest: Any) -> str:
        key = warm_key(*args, **rest)
        return key if len(args) < 8 else hashlib.sha1(key.encode()).hexdigest()[:16]

    monkeypatch.setattr(key_form, "warm_key", _changed_on_the_recode_path)
    assert key_form._stamp() != before, "отпечаток формы не заметил правку способа счёта"
    assert before == key_form.KEY_FORM, "отпечаток сборки считается не тем же способом"
