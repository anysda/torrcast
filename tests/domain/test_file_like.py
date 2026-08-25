"""Зеркало :mod:`torrcast.domain.file_like`: чем правила серий видят файл раздачи."""

from torrcast.domain.file_like import FileLike
from torrcast.domain.torr_file import TorrFile


def test_a_real_file_of_the_swarm_answers_the_whole_contract() -> None:
    """Договор нужен затем, чтобы правила серий не знали про службу раздач.

    Мера тут - что настоящий файл под него подходит и читается через него целиком:
    отвались у файла одно из трёх имён, и разбор серий остался бы без номера, имени
    или размера.
    """
    file: FileLike = TorrFile(3, "Brat.S01E02.mkv", 1024)

    assert (file.index, file.name, file.size) == (3, "Brat.S01E02.mkv", 1024)
