"""Зеркало подстановки надписей: язык, запасной каталог и ключи, которых нет.

Отдельно тут сторож ключей: каждый ключ, названный в исходниках продукта, обязан
существовать в каталоге. Опечатка в ключе иначе доезжает до человека ``KeyError``-ом
на середине показа, и ни один тест кластера её не видит.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from importlib import import_module
from pathlib import Path
from string import Formatter
from typing import TypeAlias

import pytest

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import _choose_tongue, tongue

_ROOT = Path(__file__).parents[3]
_CATALOGS = _ROOT / "torrcast" / "domain" / "catalogs"
_CYRILLIC = range(ord("\u0400"), ord("\u052f") + 1)

CatalogPair: TypeAlias = tuple[str, dict[str, str], dict[str, str]]


@pytest.fixture(autouse=True)
def _restore() -> Iterator[None]:
    _coverage(_catalogs())
    was = tongue()
    yield
    _choose_tongue(was)


def _keys_named_in_sources() -> set[str]:
    found: set[str] = set()
    for path in sorted((_ROOT / "torrcast").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "phrase" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(first.value)
    return found


def _catalogs() -> list[CatalogPair]:
    clusters = sorted(
        path.name
        for path in _CATALOGS.iterdir()
        if path.is_dir() and ((path / "en.py").is_file() or (path / "ru.py").is_file())
    )
    assert clusters, "catalog guard saw 0 clusters: the discovery instrument saw nothing"

    found: list[CatalogPair] = []
    for cluster in clusters:
        sides: dict[str, dict[str, str]] = {}
        for language in ("en", "ru"):
            path = _CATALOGS / cluster / f"{language}.py"
            assert path.is_file(), f"cluster {cluster}: missing {language}.py"
            function: Callable[[], dict[str, str]] = getattr(
                import_module(f"torrcast.domain.catalogs.{cluster}.{language}"), language
            )
            sides[language] = function()
            assert sides[language], (
                f"catalog guard saw {len(clusters)} clusters, but cluster {cluster} "
                f"has 0 keys in {language}()"
            )
        found.append((cluster, sides["en"], sides["ru"]))
    return found


def _coverage(catalogs: list[CatalogPair]) -> str:
    keys = sum(len(english) + len(russian) for _, english, russian in catalogs)
    assert keys, f"catalog guard saw {len(catalogs)} clusters and 0 keys"
    return f"catalog guard inspected {len(catalogs)} clusters and {keys} catalog keys"


def _fields(value: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(value) if field is not None}


def test_english_answers_by_default() -> None:
    _choose_tongue("en")
    assert phrase("choice.question") == "What are we watching?"


def test_russian_answers_when_chosen() -> None:
    _choose_tongue("ru")
    assert phrase("choice.question") == "Что смотрим?"


def test_values_are_substituted_by_name() -> None:
    _choose_tongue("en")
    assert phrase("choice.default", picture="Dune (2021)", number=2, total=7) == (
        "Enter - “Dune (2021)”, item 2 of 7"
    )


def test_unknown_key_falls_out_loud() -> None:
    with pytest.raises(KeyError):
        phrase("choice.no_such_line")


def test_every_key_named_in_sources_exists() -> None:
    catalogs = _catalogs()
    english = {key for _, side, _ in catalogs for key in side}
    missing = sorted(_keys_named_in_sources() - english)
    assert missing == [], f"{_coverage(catalogs)}; missing source keys: {missing}"


def test_catalog_sides_have_the_same_keys() -> None:
    catalogs = _catalogs()
    coverage = _coverage(catalogs)
    differences = [
        f"cluster {cluster}: key {key!r} missing from {language}()"
        for cluster, english, russian in catalogs
        for language, keys in (
            ("en", russian.keys() - english.keys()),
            ("ru", english.keys() - russian.keys()),
        )
        for key in sorted(keys)
    ]
    assert not differences, f"{coverage}; " + "; ".join(differences)


def test_english_catalogs_contain_no_cyrillic() -> None:
    catalogs = _catalogs()
    coverage = _coverage(catalogs)
    offenders = [
        f"cluster {cluster}: key {key!r} contains Cyrillic {character!r}"
        for cluster, english, _ in catalogs
        for key, value in english.items()
        for character in value
        if ord(character) in _CYRILLIC
    ]
    assert not offenders, f"{coverage}; " + "; ".join(offenders)


def test_english_catalogs_hold_no_guillemets() -> None:
    """Английская сторона набирает “лапки”: ёлочка - кавычка русского набора."""
    catalogs = _catalogs()
    coverage = _coverage(catalogs)
    offenders = [
        f"cluster {cluster}: key {key!r} holds a guillemet {character!r}"
        for cluster, english, _ in catalogs
        for key, value in english.items()
        for character in value
        if character in "«»"
    ]
    assert not offenders, f"{coverage}; " + "; ".join(offenders)


def test_every_catalog_value_renders_in_both_languages() -> None:
    catalogs = _catalogs()
    coverage = _coverage(catalogs)
    for cluster, english, russian in catalogs:
        for key in sorted(english.keys() | russian.keys()):
            values = {
                field: "value"
                for value in (english.get(key), russian.get(key))
                if value
                for field in _fields(value)
            }
            for language in ("en", "ru"):
                _choose_tongue(language)
                try:
                    rendered = phrase(key, **values)
                except (KeyError, IndexError) as error:
                    pytest.fail(
                        f"{coverage}; cluster {cluster}: key {key!r} does not render in "
                        f"{language}: {error!r}"
                    )
                assert "{" not in rendered and "}" not in rendered, (
                    f"{coverage}; cluster {cluster}: key {key!r} leaves braces in "
                    f"{language}: {rendered!r}"
                )


def test_catalog_pairs_have_the_same_placeholders() -> None:
    catalogs = _catalogs()
    coverage = _coverage(catalogs)
    differences = [
        f"cluster {cluster}: key {key!r} has en {_fields(english[key])!r}, "
        f"ru {_fields(russian[key])!r}"
        for cluster, english, russian in catalogs
        for key in sorted(english.keys() & russian.keys())
        if _fields(english[key]) != _fields(russian[key])
    ]
    assert not differences, f"{coverage}; placeholder mismatch: " + "; ".join(differences)


def test_catalog_keys_are_unique_between_clusters() -> None:
    catalogs = _catalogs()
    coverage = _coverage(catalogs)
    owners: dict[str, list[str]] = {}
    for cluster, english, russian in catalogs:
        for key in english.keys() | russian.keys():
            owners.setdefault(key, []).append(cluster)
    duplicates = [
        f"key {key!r} occurs in clusters {', '.join(clusters)}"
        for key, clusters in sorted(owners.items())
        if len(clusters) > 1
    ]
    assert not duplicates, f"{coverage}; " + "; ".join(duplicates)
