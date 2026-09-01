"""🔴 TC-887. Заставка обновления: та же заставка, другие три вещи.

Мера тут - КАДР тем же прибором, что у установки (:mod:`tests.test_installfinal`):
install.sh гоняется в настоящем pty, поток скармливается pyte и сверяется ровно то, что
человек видит. Своего прибора у обновления нет нарочно - иначе он мерил бы свою правду.

Отличий от установки ровно три, и каждое тут названо: последнее слово («обновлено», а не
«установлено»), последний экран (список изменений, а не подсказка по командам) и шапка
(переход `1.0.0 → 1.0.2`). Всё остальное обязано совпасть, и это тоже проверяется.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_installfinal import NARROW, WIDE, Frame, _landed, _unbroken, frame

REPO = Path(__file__).parents[1]
CHANGELOG = (REPO / "docs" / "changelog").read_text(encoding="utf-8")
#: Версия, под которую заведён раздел заглушки, и записи из него. Берутся из самого
#: файла: заглушка привязана к номеру версии, и тест, знающий номер наизусть, разошёлся
#: бы с ней молча - ровно в тот раз, когда номер поднимут.
RELEASED = re.findall(r"^\[([0-9.]+)\]$", CHANGELOG, re.M)[0]
FROM = "1.0.0"


def _entries(tongue: str) -> list[str]:
    inside = CHANGELOG.split(f"[{RELEASED}]", 1)[1]
    return [line[3:] for line in inside.splitlines() if line.startswith(f"{tongue} ")]


def _upgraded(cols: int = WIDE, language: str = "ru") -> Frame:
    return frame("mock", cols, language, upgrade=FROM, version=RELEASED)


@pytest.mark.machine
def test_the_last_word_is_updated_and_never_installed() -> None:
    """Человек, которого обновили, не читает «установлено»: это разные события."""
    shot = _upgraded()
    _landed(shot)

    assert f"[OK] torrcast {FROM} → {RELEASED} обновлено." in shot.text, shot.show()
    assert "установлено" not in shot.text, shot.show()
    assert "installed successfully" not in shot.text, shot.show()


@pytest.mark.machine
def test_the_last_screen_is_the_changelog_and_not_the_command_help() -> None:
    """Подсказку по командам обновляемый уже видел - ему интересно, что изменилось."""
    shot = _upgraded()
    _landed(shot)
    _unbroken(shot)

    for entry in _entries("ru"):
        assert entry in shot.text, f"записи «{entry}» на экране нет:\n{shot.show()}"
    for taught in ("cast --help", "cast status", "cast <запрос>"):
        assert taught not in shot.text, f"вместо изменений показана подсказка:\n{shot.show()}"


@pytest.mark.machine
def test_the_header_names_the_move_while_the_work_goes_on() -> None:
    """Переход виден по ходу работы, а не только в последней строке.

    Смотреть в итоговый кадр тут нечего: шапку с фазами он и у установки не переживает.
    Поэтому мера - поток, то есть буквально нарисованное на экране за прогон.
    """
    shot = _upgraded()
    _landed(shot)
    drawn = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", shot.stream)

    assert f"torrcast  {FROM} → {RELEASED}" in drawn, "шапка не назвала перехода"


@pytest.mark.machine
def test_the_english_screen_speaks_english_end_to_end() -> None:
    shot = _upgraded(language="en")
    _landed(shot)

    assert f"[OK] torrcast {FROM} → {RELEASED} updated successfully." in shot.text, shot.show()
    for entry in _entries("en"):
        assert entry in shot.text, f"записи «{entry}» на экране нет:\n{shot.show()}"
    assert "обновлено" not in shot.text, shot.show()


@pytest.mark.machine
def test_the_changelog_belongs_to_the_version_that_was_stamped() -> None:
    """🔴 Заглушка не вправе пережить свой релиз.

    Записи ведутся руками, и раздел заведён под конкретный номер. Сборка с другим
    номером обязана сказать, что изменений не знает, - а не показать чужие. Иначе первый
    же выпуск без раздела покажет человеку вчерашние строки как сегодняшние.
    """
    shot = frame("mock", WIDE, "ru", upgrade=FROM, version="9.9.9")
    _landed(shot)

    assert "список изменений этой версии не заполнен" in shot.text, shot.show()
    for entry in _entries("ru"):
        assert entry not in shot.text, f"чужие записи показаны как свои:\n{shot.show()}"


@pytest.mark.machine
def test_a_narrow_terminal_keeps_the_frame_whole() -> None:
    """Узкий экран режет записи, а не рамку: ширина колонки меряется, а не объявляется."""
    shot = _upgraded(cols=NARROW)
    _landed(shot)
    _unbroken(shot)

    assert "обновлено" in shot.text, shot.show()


@pytest.mark.machine
def test_an_ordinary_install_is_left_exactly_as_it_was() -> None:
    """Второй вход не протёк в первый: без него заставка прежняя, до последнего слова."""
    shot = frame("mock", WIDE, "ru")
    _landed(shot)

    assert "[OK] torrcast 1.0.0 installed successfully." in shot.text, shot.show()
    assert "cast --help" in shot.text, shot.show()
    assert "→" not in shot.row("[OK]"), shot.show()
