"""🔴 TC-939, TC-948. Итоговый экран называет приёмник и дверь в другой язык.

Мера тут - КАДР, а не пересказ: install.sh гоняется в настоящем pty, поток
скармливается pyte и сверяется ровно то, что человек видит после установки.

⚠️ pyte не знает alt-screen: если бы установщик рисовал во втором буфере, наивный
снимок дал бы пустое поле, и весь набор был бы зелен на пустом множестве. Поэтому
у каждого кадра два опорных маркера. Первый - :func:`_landed`: рамка, лого и
строка `[OK] torrcast` есть только в посаженном кадре. Второй - :func:`_no_alt`:
в потоке вообще нет переключателя alt-screen, то есть смотреть некуда, кроме как
в основной буфер, и прибор смотрит именно туда.

🔴 Настоящий поиск приёмников не запускается ни разу: `cast` тут подделка, а
конфиг - свой, в песочнице. Живой mDNS достал бы телевизор владельца.
"""

from __future__ import annotations

import fcntl
import os
import pty
import re
import shutil
import struct
import subprocess
import tempfile
import termios
import time
from dataclasses import dataclass
from pathlib import Path

import pyte
import pytest

REPO = Path(__file__).parents[1]
SCRIPT = (REPO / "install.sh").read_text(encoding="utf-8")

ROWS = 24
WIDE, NARROW, TINY = 80, 40, 30
#: Переключатели второго буфера. Ни одного из них в потоке быть не должно.
ALT_SCREEN = ("\x1b[?1049h", "\x1b[?47h", "\x1b[?1047h")
ADDR = "192.0.2.10"
LONG_NAME = "Гостиная Самсунга На Втором Этаже Слева"

_FOUND = """#!/bin/sh
printf 'ТВ: {name} - {addr}\\n'
jq '.tv = "{addr}"' "$TORRCAST_CONFIG" > "$TORRCAST_CONFIG.new"
mv "$TORRCAST_CONFIG.new" "$TORRCAST_CONFIG"
exit 0
"""
_LIST = """#!/bin/sh
{body}
exit 1
"""
#: Подделки `cast --tv`. Ключ - случай, значение - тело скрипта. Настоящего поиска
#: тут нет вовсе: строки те же, что печатает `cast --tv`, и разбираются они же.
CASTS = {
    "one": _FOUND.format(name="Гостиная", addr=ADDR),
    "noname": _FOUND.format(name="", addr=ADDR).replace("ТВ:  - ", "ТВ: "),
    "long": _FOUND.format(name=LONG_NAME, addr=ADDR),
    "many": _LIST.format(
        body="printf '  1. Гостиная - 192.0.2.10\\n  2. Спальня - 192.0.2.11\\n"
        "  3. Кухня - 192.0.2.12\\n'"
    ),
    "two": _LIST.format(body="printf '  1. Гостиная - 192.0.2.10\\n  2. Спальня - 192.0.2.11\\n'"),
    "none": _LIST.format(
        body="printf 'приёмников в сети не нашёл - телевизор включён и в той же сети?\\n'"
    ),
    #: Повторная установка: `cast` звать не за чем, и если его позвали - он это
    #: запишет, а сверка увидит след.
    "again": '#!/bin/sh\nprintf "called\\n" > "$TC939_CALLED"\nexit 0\n',
    "mock": "#!/bin/sh\nexit 0\n",
}
#: Что лежит в конфиге ДО фазы приёмника.
BEFORE = {"again": ADDR, "mock": "mock"}


@dataclass(frozen=True)
class Frame:
    """Снятый кадр: строки экрана, сырой поток и код возврата."""

    lines: tuple[str, ...]
    stream: str
    rc: int
    called: bool

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def row(self, needle: str) -> str:
        """Строка экрана, в которой встретилось `needle` (первая)."""
        return next((line for line in self.lines if needle in line), "")

    def show(self) -> str:
        """Кадр целиком - чтобы отказ печатал картинку, а не одно слово."""
        rule = "+" + "-" * len(self.lines[0]) + "+"
        return "\n".join([rule, *(f"|{line}|" for line in self.lines), rule])


def _capture(case: str, cols: int, language: str) -> Frame:
    box = Path(tempfile.mkdtemp(prefix=f"tc939-{case}-"))
    try:
        return _run(case, cols, language, box)
    finally:
        shutil.rmtree(box, ignore_errors=True)


def _run(case: str, cols: int, language: str, box: Path) -> Frame:
    for name in ("bin", "cfg", "state", "hls", "motd.d"):
        (box / name).mkdir()
    tv = BEFORE.get(case)
    value = f'"{tv}"' if tv else "null"
    (box / "cfg" / "config.json").write_text(f'{{"tv": {value}}}\n', encoding="utf-8")
    cast = box / "bin" / "cast"
    cast.write_text(CASTS[case], encoding="utf-8")
    cast.chmod(0o755)
    called = box / "called"

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, cols, 0, 0))
    child = subprocess.Popen(
        ["bash", str(REPO / "install.sh"), *(("-ru",) if language == "ru" else ())],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={
            **os.environ,
            "TERM": "xterm-256color",
            "LINES": str(ROWS),
            "COLUMNS": str(cols),
            "TORRCAST_NO_ROOT": "1",
            "TORRCAST_NO_SYSTEMD": "1",
            "TORRCAST_PREFIX": str(box),
            "TORRCAST_BIN_DIR": str(box / "bin"),
            "TORRCAST_CONFIG_DIR": str(box / "cfg"),
            "TORRCAST_STATE_DIR": str(box / "state"),
            "TORRCAST_HLS_DIR": str(box / "hls"),
            "TORRCAST_INSTALL_LOG": str(box / "install.log"),
            "TORRCAST_MOTD": str(box / "motd"),
            "TORRCAST_MOTD_D": str(box / "motd.d"),
            "TORRCAST_PHASES": "receiver",
            "TC939_CALLED": str(called),
        },
        start_new_session=True,
    )
    os.close(slave)
    started = time.monotonic()
    stream = bytearray()
    while True:
        try:
            chunk = os.read(master, 65536)
            if not chunk:
                break
            stream.extend(chunk)
        except OSError:  # ребёнок ушёл и закрыл свой конец
            break
        if time.monotonic() - started > 60:
            child.kill()
            break
    os.close(master)
    rc = child.wait()

    screen = pyte.Screen(cols, ROWS)
    pyte.Stream(screen).feed(stream.decode("utf-8", errors="replace"))
    return Frame(
        tuple(screen.display), stream.decode("utf-8", errors="replace"), rc, called.exists()
    )


_CACHE: dict[tuple[str, int, str], Frame] = {}


def frame(case: str, cols: int = WIDE, language: str = "ru") -> Frame:
    """Кадр случая. Прогон стоит секунду, поэтому одинаковые не повторяются."""
    key = (case, cols, language)
    if key not in _CACHE:
        _CACHE[key] = _capture(*key)
    return _CACHE[key]


def _no_alt(shot: Frame) -> None:
    """Опорный маркер прибора: во втором буфере никто не рисовал."""
    for switch in ALT_SCREEN:
        assert switch not in shot.stream, f"поток уходит в alt-screen ({switch!r}): pyte там слеп"


def _landed(shot: Frame) -> None:
    """Опорный маркер кадра: это именно тот экран, который остаётся человеку."""
    _no_alt(shot)
    assert shot.rc == 0, f"установщик не дошёл до конца: rc={shot.rc}\n{shot.show()}"
    body = shot.text
    assert "╭" in body and "╰" in body, f"рамки в кадре нет:\n{shot.show()}"
    assert "torrcast" in body, f"лого в кадре нет:\n{shot.show()}"
    assert "[OK] torrcast" in body, f"кадр снят не после посадки:\n{shot.show()}"


def _unbroken(shot: Frame) -> None:
    """Рамка не разорвана: строка, начатая бортом, бортом и кончается."""
    width = len(shot.lines[0])
    for number, line in enumerate(shot.lines):
        if not line.startswith("│"):
            continue
        assert len(line) == width and line[width - 1] == "│", (
            f"строка {number} порвала рамку:\n{shot.show()}"
        )


@pytest.mark.machine
@pytest.mark.parametrize("cols", [WIDE, NARROW])
def test_one_receiver_is_named_with_its_name_and_address(cols: int) -> None:
    """Один найденный - экран называет имя, адрес и то, что он прописан."""
    shot = frame("one", cols)
    _landed(shot)
    _unbroken(shot)
    line = shot.row("приёмник Гостиная")
    assert line, f"имени приёмника на экране нет:\n{shot.show()}"
    assert ADDR in line, f"адрес не в одной строке с именем:\n{shot.show()}"


@pytest.mark.machine
def test_a_repeat_install_names_the_address_without_a_second_search() -> None:
    """Адрес уже в конфиге: экран называет его, а поиск не запускается вовсе."""
    shot = frame("again")
    _landed(shot)
    _unbroken(shot)
    assert not shot.called, "повторная установка полезла искать заново"
    assert ADDR in shot.row(ADDR), f"экран смолчал про уже настроенный приёмник:\n{shot.show()}"


def test_the_search_is_run_once_and_its_output_feeds_the_final_screen() -> None:
    """Второго поиска нет и в тексте: `cast --tv` в фазе зовётся ровно раз."""
    body = SCRIPT.split("setup_receiver() {", 1)[1].split("\n}", 1)[0]
    assert body.count('"$BIN_DIR/cast" --tv') == 1, "фаза приёмника ищет дважды"
    assert 'out="$(' in body, "вывод поиска не сохранён - имя брать неоткуда"


@pytest.mark.machine
@pytest.mark.parametrize("cols", [WIDE, NARROW])
def test_several_receivers_are_listed_and_the_choice_is_left_to_the_person(cols: int) -> None:
    """Найдено двое - оба в списке, и выбор назван человеку один раз."""
    shot = frame("two", cols)
    _landed(shot)
    _unbroken(shot)
    for name, addr in (("Гостиная", "192.0.2.10"), ("Спальня", "192.0.2.11")):
        line = shot.row(name)
        assert addr in line, f"{name} без адреса в списке:\n{shot.show()}"
    assert shot.text.count("cast --tv") == 1, f"подсказка cast --tv задвоилась:\n{shot.show()}"


@pytest.mark.machine
def test_a_long_list_keeps_the_hint_and_says_how_many_are_left() -> None:
    """Троих под лого не помещается - список честно говорит про остаток."""
    shot = frame("many")
    _landed(shot)
    _unbroken(shot)
    assert "Гостиная" in shot.text, f"список пуст:\n{shot.show()}"
    assert re.search(r"(и ещё|and) 2", shot.text), f"остаток не назван:\n{shot.show()}"
    assert shot.text.count("cast --tv") == 1, f"подсказка cast --tv задвоилась:\n{shot.show()}"


@pytest.mark.machine
@pytest.mark.parametrize("cols", [WIDE, NARROW])
def test_an_empty_list_is_not_silence(cols: int) -> None:
    """Не нашлось никого - экран говорит и что делать, и чем."""
    shot = frame("none", cols)
    _landed(shot)
    _unbroken(shot)
    line = shot.row("cast --tv")
    assert "приёмник" in line, f"про приёмник экран смолчал:\n{shot.show()}"
    assert shot.text.count("cast --tv") == 1, f"подсказка cast --tv задвоилась:\n{shot.show()}"


@pytest.mark.machine
def test_a_mock_stand_is_not_called_a_configured_tv() -> None:
    """`tv: mock` - стенд без каста наружу, и «телевизор настроен» про него ложь."""
    shot = frame("mock")
    _landed(shot)
    _unbroken(shot)
    line = shot.row("mock")
    assert line, f"про mock-стенд экран смолчал:\n{shot.show()}"
    assert "настроен" not in line, f"стенд назван настроенным телевизором:\n{shot.show()}"


@pytest.mark.machine
def test_a_nameless_receiver_is_named_by_address_only() -> None:
    """Имени у устройства нет - строка остаётся про адрес, без пустого места."""
    shot = frame("noname")
    _landed(shot)
    _unbroken(shot)
    line = shot.row(ADDR)
    assert line.strip(), f"адреса на экране нет:\n{shot.show()}"
    assert " - " not in line, f"в строке остался след пустого имени:\n{shot.show()}"


@pytest.mark.machine
def test_a_long_name_is_cut_and_not_wrapped() -> None:
    """Длинное имя режется: перенос выдавил бы рамку и адрес."""
    shot = frame("long", NARROW)
    _landed(shot)
    _unbroken(shot)
    assert LONG_NAME not in shot.text, f"длинное имя влезло целиком - режь стенд:\n{shot.show()}"
    assert "Слева" not in shot.text, f"хвост имени перенесён на другую строку:\n{shot.show()}"
    assert "Гостиная" in shot.row("приёмник"), f"от имени не осталось ничего:\n{shot.show()}"


@pytest.mark.machine
@pytest.mark.parametrize("cols", [WIDE, NARROW])
@pytest.mark.parametrize(
    ("language", "door", "shut"),
    [("ru", "cast --en", "cast --ru"), ("en", "cast --ru", "cast --en")],
)
def test_the_final_screen_shows_the_door_to_the_other_language(
    cols: int, language: str, door: str, shut: str
) -> None:
    """🔴 TC-948. Дверь показана одна - та, в которую человеку идти."""
    shot = frame("one", cols, language)
    _landed(shot)
    _unbroken(shot)
    line = shot.row(door)
    assert line, f"перехода на другой язык на экране нет:\n{shot.show()}"
    assert ("English" if language == "ru" else "русский") in line, (
        f"дверь не названа тем языком, в который ведёт:\n{shot.show()}"
    )
    assert shut not in shot.text, f"показаны обе двери сразу:\n{shot.show()}"


@pytest.mark.machine
def test_the_narrowest_tier_keeps_the_tv_and_drops_the_language() -> None:
    """Тир M держит одну команду, и это `cast --tv`: язык человек уже выбрал сам."""
    shot = frame("one", TINY)
    _landed(shot)
    _unbroken(shot)
    assert "cast --tv" in shot.text, f"в узком тире не осталось команды:\n{shot.show()}"
    assert "cast --en" not in shot.text, f"узкий тир занят языком, а не ТВ:\n{shot.show()}"
    assert ADDR in shot.text, f"про приёмник смолчали и тут:\n{shot.show()}"
