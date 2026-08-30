"""Зеркало :mod:`torrcast.usecases.choice._ctl`: диагностический пульт показа.

Команда одноразовая: файл съедается до исполнения, и повторить её на следующем опросе
нельзя даже при осечке приёмника - иначе одна опечатка мотала бы фильм вечно.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.position import Position
from torrcast.usecases.choice._ctl import _ctl, _Revivable, _Steerable


class Plain:
    """Приёмник без пульта: играть умеет, а мотать его нечем."""

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        return Position(0.0, 0.0)


class Pult(Plain):
    """Приёмник, которым можно управлять как с пульта; запоминает, что с ним делали."""

    def __init__(self, breaks: bool = False) -> None:
        self.done: list[str] = []
        self.breaks = breaks

    def seek(self, pos: float) -> None:
        if self.breaks:
            raise RuntimeError("приёмник не отозвался")
        self.done.append(f"seek {pos}")

    def pause(self) -> None:
        self.done.append("pause")

    def resume(self) -> None:
        self.done.append("resume")


class Revival(Plain):
    """Приёмник с собственным терпением: погасший показ он умеет поднять заново."""

    def replay(self, at: float) -> float:
        return at


def test_a_command_from_the_file_reaches_the_receiver_and_is_said_out_loud() -> None:
    """Команда исполняется и печатается: диагностика молчащей быть не может."""
    receiver = Pult()

    with outside(Outside(command="seek 930")):
        _ctl(receiver)

    assert receiver.done == ["seek 930.0"]


def test_each_handle_of_the_pult_is_wired_to_its_own_word() -> None:
    """``pause`` и ``play`` - разные ручки, и перепутать их значит остановить показ."""
    paused, resumed = Pult(), Pult()

    with outside(Outside(command="pause")):
        _ctl(paused)
    with outside(Outside(command="play")):
        _ctl(resumed)

    assert paused.done == ["pause"] and resumed.done == ["resume"]


def test_the_file_is_eaten_before_the_command_is_carried_out() -> None:
    """Команда одноразовая: второй опрос её уже не видит, даже если она не сыграла.

    Повторись она - одна опечатка мотала бы фильм вечно, по разу на каждый опрос места.
    """
    receiver = Pult(breaks=True)
    world = Outside(command="seek 930")

    with outside(world):
        _ctl(receiver)
        _ctl(receiver)

    assert world.reads == 2 and world.command is None
    assert receiver.done == [], "приёмник отказал, и повторять за него никто не стал"


def test_a_receiver_without_a_pult_is_left_alone_and_the_command_is_still_eaten() -> None:
    """Управлять нечем - молчим; но файл прочитан, и висеть до следующего показа он не будет."""
    world = Outside(command="seek 930")

    with outside(world):
        _ctl(Plain())

    assert world.reads == 1 and world.command is None
    assert world.said == [], "исполнять было нечего - и говорить не о чем"


def test_an_empty_file_is_not_a_command_and_says_nothing() -> None:
    """Пустая строка - это не команда: печатать «пульт: » незачем."""
    world = Outside(command="")
    receiver = Pult()

    with outside(world):
        _ctl(receiver)

    assert world.said == [] and receiver.done == []


def test_with_no_file_at_all_nothing_happens_which_is_the_usual_path() -> None:
    """Файла нет - обычный путь показа, и пульт в нём не участвует ничем."""
    world = Outside(command=None)
    receiver = Pult()

    with outside(world):
        _ctl(receiver)

    assert world.said == [] and receiver.done == []


def test_an_unknown_word_is_echoed_but_touches_no_handle() -> None:
    """Незнакомое слово печатается и не делает ничего: гадать за диагноста нечего."""
    world = Outside(command="fly 42")
    receiver = Pult()

    with outside(world):
        _ctl(receiver)

    assert world.said == [phrase("choice.remote_command", command="fly 42")] and receiver.done == []


def test_a_broken_number_never_takes_the_show_down_with_it() -> None:
    """Опечатка в числе гасится: диагностика не вправе ронять показ.

    ``seek abc`` - это ошибка того, кто пишет в файл, и стоить она может ровно одной
    несработавшей команды, а не прерванного вечера.
    """
    world = Outside(command="seek abc")
    receiver = Pult()

    with outside(world):
        _ctl(receiver)

    assert (
        world.said == [phrase("choice.remote_command", command="seek abc")] and receiver.done == []
    )


def test_a_receiver_that_answers_the_pult_handles_is_recognised_by_them() -> None:
    """Управляемость опознаётся по трём ручкам разом, а не по имени класса."""
    assert isinstance(Pult(), _Steerable) is True
    assert isinstance(Plain(), _Steerable) is False


def test_a_receiver_with_its_own_patience_is_recognised_by_its_replay() -> None:
    """Воскрешать имеет смысл лишь тот приёмник, у которого есть собственное терпение.

    Признак отдельный от управляемости намеренно: мотать умеет и тот, кто поднять
    погасший показ не может.
    """
    assert isinstance(Revival(), _Revivable) is True
    assert isinstance(Pult(), _Revivable) is False
