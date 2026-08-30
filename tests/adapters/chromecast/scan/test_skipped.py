"""Строка о необойденных подсетях: одна на все, и с готовым выходом для человека."""

from __future__ import annotations

from torrcast.adapters.chromecast.scan.skipped import skipped


def test_all_the_huge_subnets_are_named_in_one_line() -> None:
    """На хосте с docker'ом широких подсетей сразу три, и три абзаца прячут сам список.

    Поэтому строка одна, и совет «задай адрес руками» в ней тоже один.
    """
    said = skipped(["10.5.0.0/16", "172.30.0.0/16", "172.17.0.0/16"])

    assert said.count("cast --tv <ip>") == 1
    assert "10.5.0.0/16" in said and "172.30.0.0/16" in said and "172.17.0.0/16" in said


def test_the_line_names_the_subnet_and_the_way_out_word_for_word() -> None:
    """Строка - единственное, ради чего модуль существует: человеку нужен выход, а не факт."""
    assert skipped(["10.5.0.0/16", "172.30.0.0/16"]) == (
        "subnets too large to scan: 10.5.0.0/16, 172.30.0.0/16 - if the TV is in one "
        "of them, give its address by hand: cast --tv <ip>"
    )


def test_nothing_skipped_is_nothing_said() -> None:
    """Обошли всё - и говорить не о чем: пустая строка перед меню была бы шумом."""
    assert skipped([]) == ""
