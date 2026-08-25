"""Договор слота внешнего мира: чем именно композиционный корень обязан его заполнить.

Голое объявление в модуле (``_play_detect: Callable[[Config], Choice]``) - это заявка
корню, и названа заявка типом. Вопрос к собранному приложению поэтому один: подходит ли
положенное под названный тип. ``hasattr`` отвечает не на него - перепутанный слот он
видит занятым, и показ падает уже на вызове.
"""

from __future__ import annotations

import ast
import inspect
import typing
from collections.abc import Callable
from inspect import Parameter, Signature
from pathlib import Path
from types import ModuleType
from typing import Any, Final

#: Довод, которым договор пробует зов: сам он никуда не уходит, зов только связывается.
_PROBE: Final = object()
_Shape = tuple[list[object], dict[str, object]]


def slots(source: str) -> list[str]:
    """Имена, объявленные в модуле без значения: «сюда положит корень»."""
    return [
        node.target.id
        for node in ast.parse(source).body
        if isinstance(node, ast.AnnAssign)
        and node.value is None
        and isinstance(node.target, ast.Name)
    ]


def _hints(module: ModuleType) -> dict[str, Any]:
    """Договоры слотов как объекты, а не как строки.

    Часть договоров названа именем из-под ``TYPE_CHECKING`` - в готовом приложении такого
    имени нет вовсе. Тогда блок выполняется поверх словаря самого модуля: это ровно тот
    же импорт, который тайпчекер делает у себя.
    """
    try:
        return typing.get_type_hints(module)
    except NameError:
        pass
    space = dict(vars(module))
    source = Path(str(module.__file__)).read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.If) and ast.unparse(node.test).endswith("TYPE_CHECKING"):
            exec(compile(ast.Module(node.body, []), str(module.__file__), "exec"), space)
    return typing.get_type_hints(module, localns=space)


def _shapes(params: list[Parameter]) -> list[_Shape]:
    """Два зова договора: одними обязательными доводами и всеми, какие он вправе передать."""
    least: _Shape = ([], {})
    most: _Shape = ([], {})
    for one in params:
        if one.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            continue
        for args, keywords in (most, *((least,) if one.default is Parameter.empty else ())):
            if one.kind is Parameter.KEYWORD_ONLY:
                keywords[one.name] = _PROBE
            else:
                args.append(_PROBE)
    return [least, most]


def _spell(shape: _Shape) -> str:
    """Зов договора словами: ``(_, _, timeout=_)``."""
    return "(" + ", ".join(["_"] * len(shape[0]) + [f"{name}=_" for name in shape[1]]) + ")"


def _call_mismatch(value: object, params: list[Parameter] | None) -> str | None:
    """Чем зов договора не сходится с тем, что положено в слот."""
    if not callable(value):
        return f"договор зовут, а положено {type(value).__name__}"
    if params is None:
        return None
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        # Встроенное без сигнатуры: сверять нечем, и выдумывать ответ хуже, чем молчать.
        return None
    for shape in _shapes(params):
        try:
            signature.bind(*shape[0], **shape[1])
        except TypeError:
            return f"договор зовёт {_spell(shape)}, а положено {_named(value)}{signature}"
    return None


def _named(value: object) -> str:
    return str(getattr(value, "__qualname__", type(value).__name__))


def _own_params(declared: Callable[..., object]) -> list[Parameter]:
    """Доводы метода договора без ``self``: зовут-то не класс, а положенное в слот."""
    return list(Signature.from_callable(declared).parameters.values())[1:]


def _protocol_mismatch(value: object, contract: type) -> str | None:
    """Чем положенное расходится с портом: нет имени или у имени другой зов."""
    members = sorted(getattr(contract, "__protocol_attrs__", ()))
    if "__call__" in members or not members:
        return _call_mismatch(value, _own_params(contract.__call__))
    for member in members:
        if not hasattr(value, member):
            return f"договор {contract.__name__} просит {member}, а его нет"
        declared = getattr(contract, member, None)
        if inspect.isfunction(declared):
            reason = _call_mismatch(getattr(value, member), _own_params(declared))
            if reason is not None:
                return f"{member}: {reason}"
    return None


def mismatch(value: object, contract: Any) -> str | None:
    """Чем положенное в слот расходится со своим договором; ``None`` - сходится."""
    if contract is Any:
        return None
    if isinstance(contract, type) and getattr(contract, "_is_protocol", False):
        return _protocol_mismatch(value, contract)
    if typing.get_origin(contract) is Callable:
        shape = typing.get_args(contract)[0]
        if shape is Ellipsis:
            # `Callable[..., X]`: договор сам не называет доводов, сверять нечего.
            return _call_mismatch(value, None)
        return _call_mismatch(
            value, [Parameter(f"_{n}", Parameter.POSITIONAL_ONLY) for n in range(len(shape))]
        )
    if isinstance(contract, type):
        if isinstance(value, contract):
            return None
        return f"договор {contract.__name__}, а положено {type(value).__name__}"
    return None


def unfit(module: ModuleType) -> list[str]:
    """Слоты модуля, которые корень оставил пустыми или заполнил не по договору."""
    declared = slots(Path(str(module.__file__)).read_text(encoding="utf-8"))
    empty = [name for name in declared if not hasattr(module, name)]
    if empty:
        # Пустые слоты называются ДО чтения договоров: чтение импортирует чужие модули, а
        # соседний импорт - ровно тот способ, которым среда раздаётся мимо корня.
        return [f"{module.__name__}.{name}: корень не положил ничего" for name in empty]
    hints = _hints(module)
    found = []
    for name in declared:
        reason = mismatch(getattr(module, name), hints[name])
        if reason is not None:
            found.append(f"{module.__name__}.{name}: {reason}")
    return found
