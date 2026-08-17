"""Ответ командной строки: чем бы команда ни кончилась, наружу идёт код возврата."""

from __future__ import annotations

from torrcast import cli
from torrcast.cli.answered import answered


def test_a_planned_stop_of_the_show_is_a_success_not_a_failure() -> None:
    """`cast stop` обязан оставлять юнит кодом 0.

    SIGTERM от `cast stop` поднимает исключение — иначе показ не пройдёт через ``finally``
    и не запишет позицию. Но исключение это штатное, и выходить на нём кодом 2 нельзя:
    systemd помечает юнит ``failed``, и после каждой нормальной остановки пользователь видит
    красную строку в статусе. Ctrl-C на вопросе отказом при этом быть не перестаёт.

    Команда сюда приходит аргументом (:func:`torrcast.cli.answered.answered`) - тем же путём,
    каким её отдаёт разбор аргументов боевого запуска.
    """
    caught: list[BaseException] = []

    def terminated() -> int:
        try:
            cli._on_term(15, None)
        except BaseException as exc:  # ловим ровно затем, чтобы посмотреть на него
            caught.append(exc)
            raise
        return int(cli.EXIT_OK)

    assert answered(terminated) == cli.EXIT_OK, "`cast stop` - успех показа, а не отказ"
    assert isinstance(caught[0], KeyboardInterrupt), "раскрутка обязана идти как прежде"

    def interrupted() -> int:
        raise KeyboardInterrupt

    assert answered(interrupted) == cli.EXIT_INFRA, "Ctrl-C остаётся отказом"
