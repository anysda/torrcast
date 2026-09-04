"""Флаги, названные человеком, которых путь показа не читает."""

from __future__ import annotations

from dataclasses import fields

import pytest

from torrcast.cli.parse_args import parse_args
from torrcast.cli.stray_flags import _FLAG, stray_flags
from torrcast.domain.args import Args

#: Поля :class:`Args`, которых человек флагом не называет: запрос приезжает словами, а
#: две подписи раздач продукт выставляет себе сам по ходу запуска.
_UNSPOKEN = frozenset({"query", "release_hash", "dead_hash"})


def test_every_field_a_person_names_has_its_flag_in_the_list() -> None:
    """🔴 Полнота списка и есть вся мера: поле без флага показ примет молча.

    Сверка идёт с полями :class:`Args`, а не с самим списком: новый флаг заводит новое
    поле, и тогда его обязаны либо назвать флагом, либо объявить внутренним. Список,
    сверяемый сам с собой, пропустил бы ровно тот случай, ради которого заведён.
    """
    assert frozenset(_FLAG) | _UNSPOKEN == {item.name for item in fields(Args)}


@pytest.mark.parametrize(
    ("argv", "stray"),
    [
        ([], []),
        (["моана"], []),
        # Флаги показа: их он читает сам, и «продолжи последнее» ими не отменяется.
        (["--dry"], []),
        (["--new"], []),
        (["--menu"], []),
        (["--voice", "2"], []),
        # Лента и настройка ТВ - чужая работа, и на показе их флаги никто не читает.
        (["--since", "2h"], ["--since"]),
        (["--tv", "10.0.0.50", "моана"], ["--tv"]),
        (["--tv", "10.0.0.50", "--since", "2h", "моана"], ["--tv", "--since"]),
    ],
)
def test_the_answer_names_only_what_the_show_does_not_read(
    argv: list[str], stray: list[str]
) -> None:
    assert stray_flags(parse_args(argv)) == stray


def test_the_language_flag_is_understood_because_the_entry_point_remembers_it() -> None:
    """`cast --ru моана` играет мумию и запоминает язык (:func:`torrcast.cli.main.main`).

    Сам сценарий показа `language` не читает, и без этой оговорки флаг языка рядом с
    запросом стал бы «непонятым» - то есть отказом там, где сегодня работа.
    """
    assert stray_flags(parse_args(["--ru", "моана"])) == []
