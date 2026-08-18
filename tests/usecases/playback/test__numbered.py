"""Зеркало договора о разобранной строке запуска: показу нужен один номер файла."""

from __future__ import annotations

from torrcast.cli.args import Args
from torrcast.usecases.playback._numbered import _Numbered


def test_the_real_args_answer_the_named_contract() -> None:
    """Полный разбор строки сюда не приходит: показ читает ровно ``--file N``."""
    named: _Numbered = Args(query=["кино"], file=3)

    assert named.file == 3


def test_a_bare_query_names_no_file_at_all() -> None:
    """Ручку не назвали - номера нет, и файл выберется сам."""
    named: _Numbered = Args(query=["кино"])

    assert named.file is None
