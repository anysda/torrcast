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

#: 🔴 Первой строкой КАЖДОЙ подделки - отметка о вызове. Считаются вызовы, а не
#: вхождения текста в install.sh: второй `cast --tv`, вписанный строкой ниже - в
#: `receiver_choice` или в любую другую функцию, - текстовую сверку одной функции
#: не тревожит, а счётчик вызовов ловит его в каждом случае.
#: 🔴 Путь счётчика ВШИВАЕТСЯ в текст подделки при записи, а не берётся из
#: окружения: измеряемый код наследует окружение и мог бы отвести второй вызов в
#: `/dev/null`, подсунув `TC939_CALLED`. Вшитый путь ему не переписать.
_CALLED = "@CALLED@"
_MARK = f'#!/bin/sh\nprintf "call\\n" >> "{_CALLED}"\n'
_FOUND = (
    _MARK
    + """printf 'ТВ: {name} - {addr}\n'
jq '.tv = "{addr}"' "$TORRCAST_CONFIG" > "$TORRCAST_CONFIG.new"
mv "$TORRCAST_CONFIG.new" "$TORRCAST_CONFIG"
exit 0
"""
)
_LIST = (
    _MARK
    + """{body}
exit 1
"""
)
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
    #: Повторная установка и mock-стенд: звать `cast` не за чем вовсе, и отметка
    #: тут стоит ровно затем, чтобы вызов было видно, если его всё же сделают.
    "again": _MARK + "exit 0\n",
    "mock": _MARK + "exit 0\n",
}
#: Что лежит в конфиге ДО фазы приёмника.
BEFORE = {"again": ADDR, "mock": "mock"}


@dataclass(frozen=True)
class Frame:
    """Снятый кадр: строки экрана, сырой поток и код возврата."""

    lines: tuple[str, ...]
    stream: str
    rc: int
    calls: int  # сколько раз реально запустился `cast --tv`

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


def _capture(case: str, cols: int, language: str, rows: int, locale: str) -> Frame:
    box = Path(tempfile.mkdtemp(prefix=f"tc939-{case}-"))
    try:
        return _run(case, cols, language, box, rows, locale)
    finally:
        shutil.rmtree(box, ignore_errors=True)


def _run(case: str, cols: int, language: str, box: Path, rows: int, locale: str) -> Frame:
    for name in ("bin", "cfg", "state", "hls", "motd.d"):
        (box / name).mkdir()
    tv = BEFORE.get(case)
    value = f'"{tv}"' if tv else "null"
    (box / "cfg" / "config.json").write_text(f'{{"tv": {value}}}\n', encoding="utf-8")
    called = box / "called"
    cast = box / "bin" / "cast"
    cast.write_text(CASTS[case].replace(_CALLED, str(called)), encoding="utf-8")
    cast.chmod(0o755)

    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    child = subprocess.Popen(
        ["bash", str(REPO / "install.sh"), *(("-ru",) if language == "ru" else ())],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={
            **os.environ,
            "TERM": "xterm-256color",
            "LC_ALL": locale,
            "LANG": locale,
            "LINES": str(rows),
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

    screen = pyte.Screen(cols, rows)
    pyte.Stream(screen).feed(stream.decode("utf-8", errors="replace"))
    calls = len(called.read_text(encoding="utf-8").split()) if called.exists() else 0
    return Frame(tuple(screen.display), stream.decode("utf-8", errors="replace"), rc, calls)


_CACHE: dict[tuple[str, int, str, int, str], Frame] = {}


def frame(
    case: str,
    cols: int = WIDE,
    language: str = "ru",
    rows: int = ROWS,
    locale: str = "C.UTF-8",
) -> Frame:
    """Кадр случая. Прогон стоит секунду, поэтому одинаковые не повторяются."""
    key = (case, cols, language, rows, locale)
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
    """Рамка не разорвана: строка, начатая бортом, бортом и кончается.

    Сперва считаются сами борта: на кадре, где их нет вовсе, обход ниже был бы
    зелен на пустом множестве, а это уже не мера.
    """
    width = len(shot.lines[0])
    walls = [number for number, line in enumerate(shot.lines) if line.startswith("│")]
    assert len(walls) >= 3, f"бортов в кадре {len(walls)} - мерить нечего:\n{shot.show()}"
    for number in walls:
        line = shot.lines[number]
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
    assert shot.calls == 0, f"повторная установка звала поиск {shot.calls} раз(а)"
    assert ADDR in shot.row(ADDR), f"экран смолчал про уже настроенный приёмник:\n{shot.show()}"


@pytest.mark.machine
@pytest.mark.parametrize(
    ("case", "times"),
    [
        ("one", 1),
        ("noname", 1),
        ("long", 1),
        ("two", 1),
        ("many", 1),
        ("none", 1),
        # Настроенный приёмник и mock-стенд: искать нечего, ноль запусков.
        ("again", 0),
        ("mock", 0),
    ],
)
def test_the_search_runs_exactly_the_promised_number_of_times(case: str, times: int) -> None:
    """🔴 Поиск - секунды mDNS, и второго человек ждать не обязан.

    Считаются ЗАПУСКИ подделки, а не вхождения текста в install.sh: второй
    `cast --tv`, вписанный соседней функцией, текстовую сверку одной функции не
    тревожит. Отдельно сверяется, что вывод поиска сохранён: имя найденного и
    список нескольких берутся из него, иначе за ними пришлось бы идти в сеть.
    Случаи с нулём тут не для полноты решётки: настроенному приёмнику и стенду
    поиск не нужен вовсе, и лишний запуск - те же секунды ожидания на пустом
    месте.
    """
    shot = frame(case)
    _landed(shot)
    assert shot.calls == times, f"`cast --tv` запускался {shot.calls} раз(а), а не {times}"
    body = SCRIPT.split("setup_receiver() {", 1)[1].split("\n}", 1)[0]
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


#: Чем язык говорит про пустой поиск. Сверяется словом, а не одной командой:
#: `cast --tv  выбрать ТВ` из колонки нашлась бы и на экране, который смолчал.
SAYS_NONE = {"ru": r"не найден|нет", "en": r"no receiver|no TV"}


@pytest.mark.machine
@pytest.mark.parametrize("language", ["ru", "en"])
@pytest.mark.parametrize("cols", [WIDE, NARROW, TINY, 25, 24, 23])
def test_an_empty_list_is_not_silence(cols: int, language: str) -> None:
    """🔴 Не нашлось никого - экран говорит и про что, и чем это чинить.

    Узкие размеры тут не для полноты решётки. На 24x30 колонка команд у вида
    `none` отдана блоку целиком (HELP_DROP съедает единственную строку тира M),
    и если блоку урезать хвост, человек остаётся без единой команды на экране.
    На 23, 24 и 25 колонках до TC-939 не было ни одной команды в обоих языках:
    короткая форма блока туда не влезала и резалась бортом.
    """
    shot = frame("none", cols, language)
    _landed(shot)
    _unbroken(shot)
    assert shot.text.count("cast --tv") == 1, (
        f"подсказки cast --tv на экране {shot.text.count('cast --tv')}:\n{shot.show()}"
    )
    line = shot.row("cast --tv")
    assert re.search(SAYS_NONE[language], line), f"экран не сказал, что не нашёл:\n{shot.show()}"


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
@pytest.mark.parametrize("language", ["ru", "en"])
@pytest.mark.parametrize("cols", [TINY, 24])
def test_the_narrowest_tier_keeps_the_tv_and_drops_the_language(cols: int, language: str) -> None:
    """Тир M держит одну команду, и это `cast --tv`: язык человек уже выбрал сам.

    🔴 Ширина 24 тут именная. Английская строка тира M шире русской на знак (21
    против 20 - `choose a TV` длиннее `выбрать ТВ`), и порог «ширина + 2» отнимал
    у английского 24-колоночного терминала единственную команду: колонки не было
    вовсе. Цифру трогать нельзя, она правдива, поэтому мерится сам экран.
    """
    shot = frame("one", cols, language)
    _landed(shot)
    _unbroken(shot)
    door = "cast --en" if language == "ru" else "cast --ru"
    assert "cast --tv" in shot.text, f"в узком тире не осталось команды:\n{shot.show()}"
    assert door not in shot.text, f"узкий тир занят языком, а не ТВ:\n{shot.show()}"
    assert ADDR in shot.text, f"про приёмник смолчали и тут:\n{shot.show()}"


@pytest.mark.machine
def test_a_byte_locale_measures_the_same_width_as_a_utf8_one() -> None:
    """🔴 Мерка чужих строк заведена ради неUTF-8 локали - там её и меряем.

    Вне UTF-8 `${#s}` в bash считает БАЙТЫ, и «Гостиная» вышла бы шириной 16:
    имя обрезалось бы вдвое раньше, чем надо. Ветка обхода по ведущим байтам
    (`UI_CHARS=0`) в UTF-8 не исполняется вовсе, поэтому кадр снимается ещё раз
    под `LC_ALL=C` и сличается со знаковым - строка в строку.
    """
    utf8 = frame("one", NARROW)
    byte = frame("one", NARROW, locale="C")
    _landed(byte)
    _unbroken(byte)
    assert byte.row("приёмник"), f"в байтовой локали строка про приёмник пропала:\n{byte.show()}"
    assert byte.row("приёмник") == utf8.row("приёмник"), (
        f"байтовая мерка разошлась со знаковой:\nбайты:\n{byte.show()}\nзнаки:\n{utf8.show()}"
    )


@pytest.mark.machine
def test_a_byte_locale_cuts_a_long_name_at_the_same_letter() -> None:
    """🔴 Обрезка (`ui_cut`) вне UTF-8 идёт по ведущим байтам - тут её и меряем.

    Мерка (`ui_len`) и обрезка - разные ветки, и короткое имя обрезку не трогает
    вовсе: «Гостиная» помещается целиком в обоих локалях. Поэтому берётся имя,
    которое РЕЖЕТСЯ, и байтовый кадр сличается со знаковым буква в букву: если
    `ui_cut` считает байты, под `LC_ALL=C` имя оборвётся вдвое раньше.
    """
    utf8 = frame("long", NARROW)
    byte = frame("long", NARROW, locale="C")
    _landed(byte)
    _unbroken(byte)
    line = byte.row("приёмник")
    assert line, f"в байтовой локали строка про приёмник пропала:\n{byte.show()}"
    assert "Гостиная Самсунг" in line, f"имя обрезано раньше времени:\n{byte.show()}"
    assert line == utf8.row("приёмник"), (
        f"байтовая обрезка разошлась со знаковой:\nбайты:\n{byte.show()}\nзнаки:\n{utf8.show()}"
    )


@pytest.mark.machine
def test_the_installation_log_line_is_cut_at_the_border() -> None:
    """Строка журнала называет путь mktemp и обязана резаться, а не рвать рамку.

    Появляется она только там, где под блоком приёмника ещё осталось место,
    поэтому кадр берётся выше обычного: на 24 строках её вытесняет приёмник.
    """
    shot = frame("one", NARROW, rows=30)
    _landed(shot)
    _unbroken(shot)
    line = shot.row("журнал установки")
    assert line, f"строки журнала в кадре нет - сторож мерил бы пустоту:\n{shot.show()}"
    assert line.endswith("│"), f"строка журнала съела борт рамки:\n{shot.show()}"


def _column(name: str, chunk: str) -> list[str]:
    """Литералы одного массива колонки команд."""
    found = re.search(rf"^\s*{name}=\( (.*) \)$", chunk, re.M)
    assert found, f"массив {name} не найден"
    return re.findall(r"'([^']*)'", found.group(1))


@pytest.mark.parametrize(
    ("cmd", "txt", "width"),
    [
        ("FIN_CMD", "FIN_TXT", "FIN_W"),
        ("FIN_CMD_S", "FIN_TXT_S", "FIN_W_S"),
        ("FIN_CMD_M", "FIN_TXT_M", "FIN_W_M"),
    ],
)
@pytest.mark.parametrize("language", ["ru", "en"])
def test_the_declared_help_width_equals_the_widest_row(
    language: str, cmd: str, txt: str, width: str
) -> None:
    """🔴 Ширина колонки задана литералом, потому что мерить её нечем.

    Задана - значит обязана равняться факту: этой же цифрой колонка центруется и
    ею же решается, влезает ли ярус. Литерал меньше факта - строка шире своей
    коробки и режется бортом; больше - ярус отказывается там, где помещался бы.
    До TC-948 в английской колонке было и то и другое (`FIN_W=41` при факте 38,
    `FIN_W_M=20` при факте 21).
    """
    head, tail = SCRIPT.split('if [ "$LANGUAGE" = en ]; then', 1)
    chunk = head if language == "ru" else tail
    rows = [len(c) + len(t) for c, t in zip(_column(cmd, chunk), _column(txt, chunk), strict=True)]
    declared = re.search(rf"^\s*{width}=(\d+)$", chunk, re.M)
    assert declared, f"ширина {width} не найдена"
    assert max(rows) == int(declared.group(1)), (
        f"{language} {width}={declared.group(1)}, а самая широкая строка {max(rows)}: {rows}"
    )
