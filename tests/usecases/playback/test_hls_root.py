"""Куда класть сегменты показа: явная настройка и переопределение окружением."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from torrcast.domain._config_hls import DEFAULT_HLS_DIR
from torrcast.usecases.playback.hls_root import HLS_ENV, hls_root

if TYPE_CHECKING:
    import pytest


def test_an_explicit_place_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Явно заданный каталог (свой ``tmp_path`` теста) сильнее подмены окружением."""
    monkeypatch.setenv(HLS_ENV, "/чужой-сандбокс")

    assert str(hls_root("/свой/tmp_path")) == "/свой/tmp_path"


def test_the_unchanged_default_yields_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Умолчание, оставшееся неизменным, уступает подмене - иначе тест уходит в боевое."""
    monkeypatch.setenv(HLS_ENV, "/сандбокс/hls")

    assert str(hls_root(DEFAULT_HLS_DIR)) == "/сандбокс/hls"


def test_without_the_environment_the_default_stays_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Подмены нет - умолчание доезжает до боевого места как было."""
    monkeypatch.delenv(HLS_ENV, raising=False)

    assert str(hls_root(DEFAULT_HLS_DIR)) == DEFAULT_HLS_DIR


def _unit_of(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    """Единица, внутри которой стоит обращение: якорь, переживающий вставку строк выше."""
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            return current.name
        current = parents.get(current)
    return "<модуль>"


def test_every_synchronous_hls_dir_access_is_guarded() -> None:
    """Новое синхронное чтение настройки ``hls_dir`` обязано явно выбрать безопасность.

    🔴 Сторож судит ИМЯ атрибута, а не имя того, у кого его берут. Привязка к голому
    ``config`` отвечала «годен» там, где мерить не могла (TC-899): дописанные в тот же
    файл ``cfg.hls_dir`` и ``holder.config.hls_dir`` - то же самое чтение той же
    настройки, - проходили молча, а ``config.hls_dir`` рядом с ними краснел.

    Вызов ``x.hls_dir(...)`` сюда не относится вовсе: это не чтение настройки, а адаптер,
    который каталог ГОТОВИТ (:func:`torrcast.adapters.stream_pack.hls_dir.hls_dir`), - его
    зовут ровно затем, чтобы место показа было чистым.

    Единственное осознанное исключение именует запасной каталог кодировщика, не готовит
    корень показа и потому не вправе звать очищающий адаптер или подменять настройку.
    Привязано оно к файлу, единице и самому выражению, а не к номеру строки: вставка
    строки выше сторожа не касается, а переписанное место - касается. Адрес с номером
    строки остаётся в самом отказе, где он и нужен человеку.
    """
    root = Path(__file__).parents[3] / "torrcast"
    allowed_bare = {
        (
            "usecases/playback/_next_warmer.py",
            "_next_warmer",
            "Path(config.hls_dir)",
        ): "только имя RECODE_DIR посреди показа; очистка корня здесь запрещена",
    }
    bare: dict[tuple[str, str, str], int] = {}
    for source in sorted(root.rglob("*.py")):
        tree = ast.parse(source.read_text(), filename=str(source))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute) and node.attr == "hls_dir"):
                continue
            parent = parents[node]
            called = isinstance(parent, ast.Call) and parent.func is node
            guarded = (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id == "hls_root"
            )
            if not called and not guarded:
                where = (
                    str(source.relative_to(root)),
                    _unit_of(node, parents),
                    ast.unparse(parent),
                )
                bare[where] = node.lineno

    assert set(bare) == set(allowed_bare), (
        "голое синхронное чтение hls_dir требует hls_root либо объяснённого исключения: "
        f"{bare}; разрешено: {allowed_bare}"
    )
