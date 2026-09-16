"""Память о висящем пульте между запусками процесса показа."""

from pathlib import Path

from tgbot.control_message import ControlMessage


def test_a_photo_remote_is_remembered_as_a_photo(tmp_path: Path) -> None:
    """Род пульта переживает перезапуск: подпись и текст правятся разными вызовами."""
    kept = ControlMessage(tmp_path / "control.message")

    kept.write(77, photo=True)

    assert kept.read() == (77, True)
    assert ControlMessage(tmp_path / "control.message").read() == (77, True)


def test_a_text_remote_is_remembered_by_its_number_alone(tmp_path: Path) -> None:
    """Текстовый пульт записан прежним видом: одно число и ничего больше."""
    kept = ControlMessage(tmp_path / "control.message")

    kept.write(42, photo=False)

    assert (tmp_path / "control.message").read_text("ascii") == "42"
    assert kept.read() == (42, False)


def test_a_remote_nobody_remembers_is_empty_instead_of_broken(tmp_path: Path) -> None:
    """Писать некуда или записи нет - память пуста, а не роняет пульт."""
    assert ControlMessage(None).read() == (0, False)
    assert ControlMessage(tmp_path / "missing").read() == (0, False)

    forgotten = ControlMessage(tmp_path / "control.message")
    forgotten.write(42, photo=False)
    forgotten.forget()

    assert forgotten.read() == (0, False)
