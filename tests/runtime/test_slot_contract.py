"""Сверщик договоров слотов: на чём он краснеет и на чём молчит.

У самого сверщика мера та же, что и у сторожа, которым он служит: перепутанный слот
обязан краснеть. Поэтому каждая проверка ниже ставит рядом подходящее и перепутанное -
зелёное на обоих было бы ровно тем ответом, купленным входом, ради которого он и заведён.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol

from tests.runtime.slot_contract import mismatch, slots, unfit


class _Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class _Grids(Protocol):
    def __call__(self, source_url: str, length: float = ...) -> str: ...


def _loaded(root: Path, source: str) -> ModuleType:
    """Собрать модуль из текста: сверщик читает объявления по файлу, а не по памяти."""
    path = root / "slotted.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("slotted", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_slots_of_a_module_are_the_bare_declarations_and_nothing_else() -> None:
    """Объявление со значением - это уже не заявка корню, а готовое имя."""
    named = slots("port: int\nready: int = 1\nplain = 2\n")

    assert named == ["port"]


def test_a_slot_the_root_never_filled_is_named_before_any_contract_is_read(tmp_path: Path) -> None:
    """Пустой слот называется первым: чтение договоров импортирует чужое."""
    module = _loaded(tmp_path, "port: int\n")

    assert unfit(module) == ["slotted.port: корень не положил ничего"]

    vars(module)["port"] = 8000

    assert unfit(module) == []


def test_a_swapped_slot_is_caught_by_the_shape_of_its_call() -> None:
    """Договор с одним доводом и бездоводное в слоте - это разные вещи."""

    def of_one(number: int) -> str:
        return str(number)

    def of_none() -> str:
        return ""

    assert mismatch(of_one, Callable[[int], str]) is None
    assert mismatch(of_none, Callable[[int], str]) is not None
    assert mismatch(of_none, Callable[..., str]) is None


def test_a_port_answers_with_every_method_it_named() -> None:
    """Порт - это список методов: нет одного, и слот занят не тем."""

    class _Whole:
        def monotonic(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            return None

    class _Half:
        def monotonic(self) -> float:
            return 0.0

    assert mismatch(_Whole(), _Clock) is None
    assert mismatch(_Half(), _Clock) == "договор _Clock просит sleep, а его нет"


def test_a_port_whose_method_takes_the_wrong_count_is_not_a_filled_slot() -> None:
    """Имя метода на месте, а зов другой: `hasattr` тут и отвечал «занято»."""

    class _Deaf:
        def monotonic(self) -> float:
            return 0.0

        def sleep(self) -> None:
            return None

    reason = mismatch(_Deaf(), _Clock)

    assert reason is not None
    assert reason.startswith("sleep: договор зовёт (_)")


def test_a_port_that_is_called_answers_for_the_shape_of_the_call() -> None:
    """У порта-зова договор держит и необязательный довод: без него слот не тот."""

    def whole(source_url: str, length: float = 0.0) -> str:
        return source_url

    def bare(source_url: str) -> str:
        return source_url

    assert mismatch(whole, _Grids) is None
    assert mismatch(bare, _Grids) is not None


def test_a_slot_of_a_plain_kind_holds_its_own_kind() -> None:
    """Порт нужен не всякому слоту: число остаётся числом."""
    assert mismatch(8000, int) is None
    assert mismatch("8000", int) == "договор int, а положено str"
