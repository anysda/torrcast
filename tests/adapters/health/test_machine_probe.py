"""Проверяет пробы машины: диск, память, серт и часы отвечают значением."""

from pathlib import Path

from torrcast.adapters.health.machine_probe import MachineProbe


def test_free_space_is_asked_of_a_living_ancestor(tmp_path: Path) -> None:
    """Каталога может не быть - место считается по ближайшему живому предку."""
    assert MachineProbe.disk_free(str(tmp_path)) > 0
    assert MachineProbe.disk_free(str(tmp_path / "нет" / "и" / "тут")) > 0


def test_an_absent_cert_is_none_and_not_a_traceback(tmp_path: Path) -> None:
    """Серта нет - это ответ «не читается», а не падение самопроверки."""
    assert MachineProbe.cert_days(str(tmp_path / "нет.crt")) is None


def test_a_junk_cert_is_none_too(tmp_path: Path) -> None:
    """Файл есть, но это не серт - тот же ответ, что и у отсутствующего."""
    junk = tmp_path / "junk.crt"
    junk.write_text("не серт")
    assert MachineProbe.cert_days(str(junk)) is None


def test_the_machine_answers_about_its_memory_and_locale() -> None:
    """Память меряется в байтах, кодировка приходит в нижнем регистре."""
    assert MachineProbe.machine_memory() > 0
    assert MachineProbe.encoding() == MachineProbe.encoding().lower()


def test_the_shelf_limits_are_numbers_and_the_clock_moves_forward() -> None:
    keys_kept, probe_kept = MachineProbe.shelf_limits()
    assert keys_kept > 0 and probe_kept > 0
    assert MachineProbe.now() > 0
    assert MachineProbe.retain_days() > 0
