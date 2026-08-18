"""Зеркало :mod:`torrcast.runtime.main`: точка входа ``cast``.

Модуль существует ради одного порядка действий, и он же тут сторожится: команда обязана
получить внешний мир УЖЕ собранным. Console-script указывает сюда, а не сразу в команду,
ровно потому, что собирать мир - дело композиционного корня, и только его.
"""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.runtime.main import main


def test_the_world_is_assembled_before_the_command_gets_to_work() -> None:
    """Сборка идёт первой, команда второй - иначе команда работает по пустым портам.

    Поменяй порядок - и первая же команда пошла бы в незаполненные порты: след молчал бы,
    состояние читалось бы мимо адаптера, а понять это по выводу было бы нельзя - выглядит
    как «просто ничего не записалось».
    """
    order: list[str] = []

    def fake_wire() -> None:
        order.append("собрали мир")

    def fake_run(argv: Sequence[str] | None) -> int:
        order.append("выполнили команду")
        return 0

    main(["status"], assemble=fake_wire, command=fake_run)

    assert order == ["собрали мир", "выполнили команду"]


def test_the_arguments_reach_the_command_untouched() -> None:
    """Точка входа ничего не разбирает сама и отдаёт аргументы команде как есть.

    Начни она их трогать - разбор жил бы в двух местах, и флаг, понятный команде, мог бы
    потеряться по дороге ещё до того, как о нём кто-нибудь узнал.
    """
    seen: list[Sequence[str] | None] = []

    def fake_run(argv: Sequence[str] | None) -> int:
        seen.append(argv)
        return 0

    main(["кино", "--release", "2"], assemble=lambda: None, command=fake_run)
    main(None, assemble=lambda: None, command=fake_run)

    assert seen == [["кино", "--release", "2"], None]


def test_the_exit_code_of_the_command_is_the_exit_code_of_the_process() -> None:
    """Код возврата команды уходит наружу нетронутым - по нему судит вызывающий.

    Проглоти точка входа неудачу - скрипт, запустивший `cast`, считал бы провалившийся
    показ успешным и пошёл бы дальше по своему сценарию.
    """
    assert main(["status"], assemble=lambda: None, command=lambda argv: 3) == 3
