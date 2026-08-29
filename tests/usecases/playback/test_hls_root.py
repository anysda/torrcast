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


def test_every_synchronous_hls_dir_access_is_guarded() -> None:
    """Новое синхронное чтение ``config.hls_dir`` обязано явно выбрать безопасность.

    Единственное осознанное исключение именует запасной каталог кодировщика, не готовит
    корень показа и потому не вправе звать очищающий адаптер или подменять настройку.
    Привязка к точной строке не пропустит новый файл либо новое обращение молча.
    """
    root = Path(__file__).parents[3] / "torrcast"
    allowed_bare = {
        (
            "usecases/playback/_next_warmer.py",
            79,
        ): "только имя RECODE_DIR посреди показа; очистка корня здесь запрещена",
    }
    bare: list[tuple[str, int]] = []
    for source in root.rglob("*.py"):
        tree = ast.parse(source.read_text(), filename=str(source))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Attribute)
                and node.attr == "hls_dir"
                and isinstance(node.value, ast.Name)
                and node.value.id == "config"
            ):
                continue
            parent = parents[node]
            guarded = (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id == "hls_root"
            )
            if not guarded:
                bare.append((str(source.relative_to(root)), node.lineno))

    assert set(bare) == set(allowed_bare), (
        "голое синхронное config.hls_dir требует hls_root либо объяснённого исключения: "
        f"{bare}; разрешено: {allowed_bare}"
    )
