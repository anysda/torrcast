"""🔴 TC-887. Заставка обновления: та же заставка, другие три вещи.

Мера тут - КАДР тем же прибором, что у установки (:mod:`tests.test_installfinal`):
install.sh гоняется в настоящем pty, поток скармливается pyte и сверяется ровно то, что
человек видит. Своего прибора у обновления нет нарочно - иначе он мерил бы свою правду.

Отличий от установки ЧЕТЫРЕ, и каждое тут названо: последнее слово («обновлено», а не
«установлено»), последний экран (список изменений, а не подсказка по командам), шапка
(переход `1.0.0 → 1.0.3`) и отпечаток установленного пакета в самой строке `[OK]`,
которого у установки нет. Всё остальное обязано совпасть, и это тоже проверяется.

⚠️ «Обычная установка осталась той же» - про ЗАСТАВКУ, не про работу: класть загрузчик в
`$PREFIX` фаза `torrcast` теперь стала при ЛЮБОЙ установке, и это правка обычной
установки (сторож - `tests/test_install.py`, тест про загрузчик рядом с venv).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from tests.test_installfinal import (
    NARROW,
    SCRIPT,
    WIDE,
    Frame,
    _landed,
    _unbroken,
    frame,
)
from torrcast.usecases.upgrade import CATALOG_CUT

REPO = Path(__file__).parents[1]
CHANGELOG = (REPO / "docs" / "changelog").read_text(encoding="utf-8")
#: Версия, под которую заведён раздел заглушки, и записи из него. Берутся из самого
#: файла: заглушка привязана к номеру версии, и тест, знающий номер наизусть, разошёлся
#: бы с ней молча - ровно в тот раз, когда номер поднимут.
RELEASED = re.findall(r"^\[([0-9.]+)\]$", CHANGELOG, re.M)[0]
#: Номер, которым помечена сборка. Тоже читается из дерева, а не наизусть: install.sh
#: печатает его человеку, и тест с зашитым номером краснеет на каждом подъёме версии.
STAMPED = re.findall(r"^VERSION='([^']*)'$", SCRIPT, re.M)[0]
FROM = "1.0.0"


def _entries(tongue: str) -> list[str]:
    """Записи ТОЛЬКО своего раздела: сразу за ним в файле лежит прошлый выпуск.

    Раздел кончается следующей шапкой `[версия]`. Без этой границы записи прошлого
    номера читаются как свои, и сторож «чужих записей не показывать» покупается молча
    в первый же подъём версии.
    """
    inside = CHANGELOG.split(f"[{RELEASED}]", 1)[1]
    inside = re.split(r"^\[[0-9.]+\]$", inside, maxsplit=1, flags=re.M)[0]
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

    assert f"[OK] torrcast {STAMPED} installed successfully." in shot.text, shot.show()
    assert "cast --help" in shot.text, shot.show()
    assert "→" not in shot.row("[OK]"), shot.show()


def _fingerprint(tree: Path) -> str:
    """Отпечаток дерева, посчитанный НЕЗАВИСИМО от установщика - питоном, по файлам.

    Иначе сторож покупается любой константой: «sha256 » и двенадцать знаков на экране
    сами по себе не говорят, чей это отпечаток и от чего он посчитан. Повторяется тут
    ровно то, что делает ``py_manifest``: строка ``<sha256>  ./путь`` на каждый файл
    (кроме байт-кода), порядок байтовый, и уже над этим списком - второй sha256.
    """
    files = sorted(
        "./" + p.relative_to(tree).as_posix()
        for p in tree.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    manifest = "\n".join(
        f"{hashlib.sha256((tree / name[2:]).read_bytes()).hexdigest()}  {name}" for name in files
    )
    return hashlib.sha256((manifest + "\n").encode()).hexdigest()[:12]


@pytest.mark.machine
def test_the_fingerprint_of_the_installed_package_is_the_fourth_difference() -> None:
    """🔴 Четвёртое отличие: отпечаток установленного пакета, и он ТОЛЬКО у обновления.

    Обновлённому нечем проверить, что переставили именно его копию, кроме этого числа,
    поэтому мера не довольствуется формой строки: то же число считается заново питоном
    по дереву репы. Совпало - на экране отпечаток настоящего пакета, а не украшение.

    Второй мерой тут стоит целость рамки, и она не про красоту: рамка ростом в экран,
    и отпечаток, напечатанный ОТДЕЛЬНОЙ строкой под `[OK]`, уносил её верх за экран.
    Так и было в первой сборке, и увидел это только кадр.

    Прогон тут не как у прочих кадров: гоняется фаза `torrcast` (в ней и живёт
    `verify_torrcast`, который отпечаток считает), а venv в песочнице подделан -
    настоящий тут не собрать. Версия, от которой идём, взята заведомо младше сборки:
    сборка не помечена, и её номер - тот, что стоит в install.sh.
    """
    older = "0.9.0"
    assert older != STAMPED, "версия перехода совпала со сборкой - обновления не будет"

    shot = frame("one", upgrade=older, phases="torrcast")
    _landed(shot)
    _unbroken(shot)

    line = shot.row("[OK]")
    assert f"[OK] torrcast {older} → {STAMPED} обновлено." in line, shot.show()
    assert f"sha256 {_fingerprint(REPO / 'torrcast')}" in line, shot.show()


@pytest.mark.machine
def test_a_narrow_screen_drops_the_fingerprint_and_keeps_the_frame() -> None:
    """Мерка ширины настоящая: в узкий экран отпечаток не лезет и уступает строке.

    🔴 Мера тут - РАВЕНСТВО строки целиком, а не отсутствие слова «sha256». Заставка
    выключает перенос, поэтому лишнее не переезжает на следующую строку, а срезается
    краем экрана: код, печатающий отпечаток безусловно, оставляет от него один мусорный
    знак в хвосте - «обновлено. a». Проверка «sha256 в кадре нет» такой брак покупает
    молча, и куплен он был: первая проба этого сторожа прошла зелёной.
    """
    shot = frame("one", cols=NARROW, upgrade="0.9.0", phases="torrcast")
    _landed(shot)
    _unbroken(shot)

    assert shot.row("[OK]").strip() == f"[OK] torrcast 0.9.0 → {STAMPED} обновлено.", shot.show()


@pytest.mark.machine
def test_an_ordinary_install_prints_no_fingerprint_line() -> None:
    """Та же фаза без обновления: отпечаток в журнале есть, а на экране его нет.

    Без этой половины первый сторож зелен и у скрипта, который печатает отпечаток
    всегда, - то есть отличием строка быть перестала бы, а докстрока файла врала бы
    дальше.
    """
    shot = frame("one", phases="torrcast")
    _landed(shot)

    assert "installed successfully" in shot.text, shot.show()
    assert "sha256" not in shot.text, shot.show()


def test_the_code_that_means_a_trimmed_catalog_is_one_number_and_not_two() -> None:
    """🔴 Двойка живёт в двух местах: `EXIT_CATALOG_CUT` в установщике и `CATALOG_CUT`
    в сценарии обновления. Каждая сторона прибита своим тестом, друг к другу - ничем,
    и разъедутся они молча: обновление начнёт звать провалом штатный исход установки.
    Значение читается из install.sh ФОРМОЙ, а не повторяется тут числом.
    """
    found = re.findall(r"^EXIT_CATALOG_CUT=([0-9]+)$", SCRIPT, re.M)
    assert len(found) == 1, "EXIT_CATALOG_CUT в install.sh нет или он не один"
    assert int(found[0]) == CATALOG_CUT
