"""Счастливый путь: фильм и озвучка, больше ничего.

Проверяется дословное требование к продукту: «не хочу видеть какие там файлы, хочу
выбрать фильм и озвучку». Значит на обязательном пути нет ни таблицы релизов, ни списка
файлов, ни строк про серии у фильма, а вопросов ровно два — и оба пропускаются, когда
выбор единственный.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from torrcast import InfraError, cli
from torrcast.search import RawResult
from torrcast.state import Config, Entry, State, save_config
from torrcast.stream import AudioTrack, Media, TorrFile

#: Настоящее ожидание картинки: фикстура окружения подменяет его заглушкой, а один тест
#: проверяет именно его.
AWAIT_PLAYING = cli._await_playing

GB = 1024**3
#: Ключ сохранённой «Moana (2016)» - записи, которую находит запрос «моана».
OLD_KEY = "movie:moana:2016"
#: Выдача «моаны», сведённая к сути: две картины франшизы, у каждой по два релиза.
FOUND = [
    RawResult("Moana 2016 1080p DSNP WEB-DL DDP5 1 Atmos H 264-BLOOM", "a" * 40, 5 * GB, 22),
    RawResult("Moana 2016 1080p BluRay x264 Atmos TrueHD7 1-WiKi", "b" * 40, 17 * GB, 5),
    RawResult("Моана 2 / Moana 2 (2024) WEB-DL 1080p | D, P", "c" * 40, 3 * GB, 140),
    RawResult("Moana 2 (2024) 1080p BRRip 5.1 x264 -YTS", "d" * 40, 2 * GB, 121),
]
TRACKS = (
    AudioTrack(0, "rus", "Дубляж", "ac3", 6),
    AudioTrack(1, "eng", "Original", "ac3", 6),
)


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Окружение без Prowlarr, без TorrServer, без systemd — но с полным путём выбора."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    save_config(Config(tv="10.0.0.50", prowlarr_apikey="ключ", hls_dir=str(tmp_path / "hls")))
    monkeypatch.setattr(cli, "Prowlarr", _FakeProwlarr)
    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(
        cli, "probe", lambda url, timeout=90.0, alive=None: Media(5978.0, TRACKS, "h264", 1080)
    )
    monkeypatch.setattr(cli, "start_play_unit", lambda key: None)
    monkeypatch.setattr(cli, "stop_play_unit", lambda: None)
    monkeypatch.setattr(cli, "_await_playing", lambda config, progress, timeout=120.0: None)


class _FakeProwlarr:
    def __init__(self, url: str, apikey: str) -> None:
        self.url = url

    def search(self, query: str) -> list[RawResult]:
        return list(FOUND)

    def late(self) -> list[RawResult]:
        """Опоздавших нет: круг тут отвечает разом (TC-118)."""
        return []

    def spare(self) -> float:
        """Остаток цели: тут поиск мгновенный, поэтому цела вся (TC-228)."""
        from torrcast.search import GOAL

        return GOAL


class _FakeTorrServer:
    """Раздача в объёме подготовки релиза: hash, файлы, URL потока."""

    def __init__(self, url: str) -> None:
        self.url = url

    def add(self, magnet: str) -> str:
        return f"hash-{magnet[:30]}"

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        return [
            TorrFile(0, "Moana/Moana.2016.1080p.mkv", 5 * GB),
            TorrFile(1, "Moana/Moana.sample.mkv", 30 * 1024**2),
            TorrFile(2, "Moana/cover.jpg", 1024),
        ]

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> bool:
        pass

        return True


def _answers(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Подставные ответы человека; заодно собираем сами вопросы."""
    asked: list[str] = []
    queue = iter(replies)

    def ask(prompt: str = "") -> str:
        asked.append(prompt)
        return next(queue, "")

    monkeypatch.setattr("builtins.input", ask)
    return asked


def test_the_happy_path_asks_about_the_film_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """На счастливом пути вопрос ровно один — «какой фильм франшизы?».

    Меню озвучки из счастливого пути убрано: дорожка выбирается сама, а её подпись
    печатается в строке запуска — молчаливой подмены тут нет, есть названный выбор.
    """
    asked = _answers(monkeypatch, "2", "")

    assert cli.main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert [q.split("[")[0].strip() for q in asked] == ["Что смотрим?"]
    assert "Озвучка:" not in printed, "меню озвучки на счастливом пути больше нет"
    assert "  1. Moana (2016)" in printed and "  2. Моана 2 (2024)" in printed
    assert "играю «Моана 2» (2024) · 1080p · rus · Дубляж - на ТВ" in printed
    # Ни таблицы релизов, ни файлов, ни серий - именно этого пользователь видеть не хочет.
    for forbidden in ("Релизы:", "Качество", "Файл:", "Серии:", ".mkv", "Какой берём?"):
        assert forbidden not in printed, forbidden
    # И ни одного значка из запрещённого набора: вывод остаётся текстом, а не пиктограммами.
    assert not set(printed) & set("→⚠▶≥")


def test_silent_indexer_is_named_once_during_search(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Урезанная выдача не выглядит полной: промолчавший источник назван на экране."""

    class _SilentProwlarr(_FakeProwlarr):
        silent = ("Knaben",)
        reported_silent: set[str]

        def __init__(self, url: str, apikey: str) -> None:
            super().__init__(url, apikey)
            self.reported_silent = set()

    monkeypatch.setattr(cli, "Prowlarr", _SilentProwlarr)
    _answers(monkeypatch, "2", "")

    assert cli.main(["моана"]) == 0
    printed = capsys.readouterr().out
    line = "индексер Knaben не ответил - выдача может быть хуже"
    assert printed.count(line) == 1


def test_banned_indexer_is_named_too(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-510. Выпасть из каталога можно двумя способами, и оба видны человеку: молчун
    не ответил нам, а заблокированного мы и не спрашивали (TC-259). Строка при этом одна
    и на весь поиск одна - разводить их по кругам поиска незачем."""

    class _BannedProwlarr(_FakeProwlarr):
        banned = ("Knaben",)
        reported_silent: set[str]

        def __init__(self, url: str, apikey: str) -> None:
            super().__init__(url, apikey)
            self.reported_silent = set()

    monkeypatch.setattr(cli, "Prowlarr", _BannedProwlarr)
    _answers(monkeypatch, "2", "")

    assert cli.main(["моана"]) == 0
    printed = capsys.readouterr().out
    assert printed.count("индексер Knaben недоступен - выдача может быть хуже") == 1


def test_the_question_says_out_loud_what_enter_will_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-204. Дефолт - не первая строка меню, а в длинной франшизе он и за экраном:
    терминал после вывода показывает хвост. Поэтому прямо перед вопросом сказано, что
    случится по Enter, - названием и годом, а не одной цифрой в скобках.

    Строка стоит ПОСЛЕ списка: шапка уехала бы вверх вместе со списком. Сам список
    остаётся хронологическим - меняется показ дефолта, а не порядок.
    """
    _answers(monkeypatch, "", "")  # Enter на вопросе - то самое, о чём строка и говорит

    assert cli.main(["моана"]) == 0

    printed = capsys.readouterr().out
    enter = "Enter - «Moana (2016)», пункт 1 из 2"
    assert enter in printed
    assert (
        printed.index("  1. Moana (2016)")
        < printed.index("  2. Моана 2 (2024)")
        < printed.index(enter)
    ), "список хронологический, а строка про дефолт - в хвосте, у самого вопроса"
    assert "играю «Moana»" in printed, "и Enter запустил ровно то, что было названо"


def test_a_single_choice_is_not_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Меню франшизы пропускается, когда картина одна; озвучки нет вовсе."""
    monkeypatch.setattr(
        cli, "probe", lambda url, timeout=90.0, alive=None: Media(5978.0, TRACKS[:1], "h264")
    )
    asked = _answers(monkeypatch)

    assert cli.main(["моана", "2"]) == 0

    assert asked == [], "выбирать не из чего - спрашивать не о чем"
    assert "Озвучка:" not in capsys.readouterr().out


def test_a_bare_enter_is_enough_for_everything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Любой вопрос принимает пустой Enter: русский ввод допустим, но не обязателен.

    Enter приводит в ПЕРВУЮ ЖИВУЮ часть франшизы, а не в самую обсиженную: «моана» -
    это просьба про «Moana» 2016 с её 22 сидами, даже когда у «Моаны 2» их 140
    (🔴 TC-196). Список при этом остаётся хронологическим.
    """
    _answers(monkeypatch, "", "")

    assert cli.main(["моана"]) == 0
    printed = capsys.readouterr().out
    assert "  1. Moana (2016)\n  2. Моана 2 (2024)" in printed, "список остался хронологией"
    assert "играю «Moana» (2016)" in printed


#: Выдача «мумии»: две картины под одним именем - самая тихая из подмен (🔴 TC-198).
TWINS = [
    RawResult("Мумия / The Mummy (1999) BDRip 1080p | D", "e" * 40, 5 * GB, 47),
    RawResult("Мумия / The Mummy (2026) WEB-DL 1080p | D", "f" * 40, 4 * GB, 604),
]


def test_the_swap_line_is_the_last_word_before_the_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-198: взяли не то, что назвали, - и человек слышит об этом ПЕРЕД стартом.

    Место у строки одно и выбрано не для порядка: фазы поиска к этой секунде уехали
    вверх экрана и читаются как ход работы, а решение про картину человек уносит с
    собой. Раньше на «мумию» не печаталось ничего вовсе - тихо игралась та «Мумия»,
    у которой рой пожирнее.
    """

    class _Twins(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return list(TWINS)

    monkeypatch.setattr(cli, "Prowlarr", _Twins)
    _answers(monkeypatch, "", "")

    assert cli.main(["мумия"]) == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines[-1].startswith("играю «Мумия» (1999)"), lines[-1]
    assert lines[-2] == (
        "спросили «мумия» - беру «Мумия (1999)»: под этим именем есть ещё "
        "«Мумия (2026)» - другая картина"
    ), lines[-2]


def test_the_film_with_a_number_in_the_title_is_a_film(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Номер в названии не делает картину сериалом: «Моана 2» — фильм, строк про серии нет."""
    _answers(monkeypatch, "2", "")

    assert cli.main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert "сериал" not in printed and "s1e1" not in printed
    key, entry = next(iter(State.load()))
    assert (key, entry.kind, entry.episodes) == ("movie:моана-2:2024", "movie", [])


def test_without_a_terminal_an_ambiguous_franchise_is_refused_not_guessed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Без терминала «дефолт» на вопросе про франшизу — это чужой фильм, пущенный молча.

    Ровно так и вышло на прогоне без tty: вопрос взял первый пункт вслепую, а `--new` к
    тому времени уже снёс сохранённую запись. Теперь ни того, ни другого: висеть на
    вопросе нельзя — мы и не висим, но отказываемся вслух и подсказываем, как назвать
    картину точно. Сохранённое место при этом цело.
    """
    from torrcast import console

    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    monkeypatch.setattr(cli, "start_play_unit", lambda key: pytest.fail("вслепую не кастим"))
    _remember_moana()

    assert cli.main(["моана", "--new"]) == 1

    printed = capsys.readouterr()
    assert "1. Moana (2016)" in printed.out and "2. Моана 2 (2024)" in printed.out
    assert "вслепую не выбираю" in printed.err and "Moana" in printed.err
    kept = State.load().get(OLD_KEY)
    assert kept is not None and kept.pos == 2467.0, "сохранённую позицию не трогаем никогда"


def test_a_pick_names_the_film_without_a_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """Картину можно назвать флагом - тогда вопроса «Что смотрим?» нет вовсе.

    Номер - ровно тот, что стоит у пункта меню на экране, и называет его человек:
    молчаливой подмены тут нет, есть названный выбор, как у ``--release`` и ``--voice``.
    """
    asked = _answers(monkeypatch)

    assert cli.main(["моана", "--pick", "2"]) == 0

    assert asked == [], "номер назван флагом - спрашивать нечего"
    key, _entry = next(iter(State.load()))
    assert key == "movie:моана-2:2024"


def test_a_pick_works_where_a_menu_cannot_be_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без терминала меню упирается в честный отказ - а с флагом картина названа и там.

    Это и есть назначение флага: любой неинтерактивный сценарий (ssh без pty, скрипт)
    называет номер заранее и не упирается в вопрос, на который некому ответить.
    """
    from torrcast import console

    monkeypatch.setattr(console, "stdin_is_tty", lambda: False)
    _answers(monkeypatch)

    assert cli.main(["моана", "--pick", "1"]) == 0

    key, _entry = next(iter(State.load()))
    assert key == "movie:moana:2016"


def test_a_pick_outside_the_menu_is_an_honest_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Номер, которого нет в меню, - ошибка вслух, а не молчаливый первый пункт."""
    monkeypatch.setattr(cli, "start_play_unit", lambda key: pytest.fail("не кастим"))
    _answers(monkeypatch)

    assert cli.main(["моана", "--pick", "7"]) == 1
    assert "номера 7 нет" in capsys.readouterr().err


def test_new_forgets_the_old_record_only_when_the_show_really_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Обещание `--new` («забыть прогресс») в силе — но платим по нему в момент старта.

    До старта стирать нечего и незачем: свежую запись всё равно кладёт запуск показа, а
    любой обрыв раньше него оставил бы пользователя без позиции.
    """
    _answers(monkeypatch, "2", "")
    _remember_moana()

    assert cli.main(["моана", "--new"]) == 0

    left = State.load()
    assert left.get(OLD_KEY) is None, "показ пошёл - прежний прогресс забыт, как и просили"
    assert left.entries["movie:моана-2:2024"].pos == 0.0


def _remember_moana() -> None:
    """Недосмотренная «Moana» в состоянии: её и находит запрос «моана»."""
    state = State()
    state.put(
        OLD_KEY,
        Entry(title="Moana", magnet="magnet:?xt=1", query="моана", pos=2467.0, dur=5978.0),
    )
    state.save()


def test_release_and_file_are_debug_handles_and_show_the_insides(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--release N` и `--file N` — отладочные ручки: внутренности показываем только им."""
    _answers(monkeypatch, "1", "")

    assert cli.main(["моана", "2", "--release", "2", "--file", "1"]) == 0

    printed = capsys.readouterr().out
    assert "файл: Moana.2016.1080p.mkv" in printed
    assert State.load().entries["movie:моана-2:2024"].file_idx == 0


def test_a_hand_picked_number_does_not_trip_the_neighbours_prewarm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Названный номер относится к выбранной картине, а греются под меню все.

    Прогрев поднимает голову очереди у первых картин списка (:data:`~torrcast.cli.PREWARM`),
    и номер, названный руками, у соседки может не существовать вовсе: у «Моаны» 2016 года
    раздачи две, а спрошена третья у «Моаны 2». Соседка на этом молчит - спрос идёт с той
    картины, которую человек выбрал.
    """
    extra = RawResult("Моана 2 / Moana 2 (2024) BDRip 1080p x264", "e" * 40, 4 * GB, 90)
    monkeypatch.setattr(_FakeProwlarr, "search", lambda self, query: [*FOUND, extra])
    _answers(monkeypatch, "2", "")

    assert cli.main(["моана", "--release", "3"]) == 0

    assert "релизов 2" not in capsys.readouterr().out, "счёт соседки к выбору не относится"


def test_releases_prints_the_old_table_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    """`cast releases <запрос>` — та самая таблица, но только по явной просьбе."""
    assert cli.main(["releases", "моана"]) == 0

    printed = capsys.readouterr().out
    assert "Релизы:" in printed and "Качество" in printed
    assert "Moana (2016)" in printed and "Моана 2 (2024)" in printed
    assert "играю" not in printed, "releases ничего не запускает"


def test_releases_ties_each_number_to_its_picture(capsys: pytest.CaptureFixture[str]) -> None:
    """🔴 TC-446. Номер релиза относится к картине своей таблицы - и таблица это говорит.

    Картин в выдаче несколько, нумерация релизов у каждой своя, и одним ``--release N``
    картину не назвать: заголовки нумеруются тем же номером, что пункты меню `cast`
    (и флаг ``--pick``), а строка-подсказка зовёт оба флага.
    """
    assert cli.main(["releases", "моана"]) == 0

    printed = capsys.readouterr().out
    assert "1. Moana (2016) - раздач" in printed, printed
    assert "2. Моана 2 (2024) - раздач" in printed, printed
    assert "--pick M --release N" in printed, printed


def test_the_start_time_means_a_picture_on_the_screen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """«Старт NN с» обязан означать картинку, а не «упаковка пошла».

    Доказательство картинки одно: показ увидел ``PLAYING`` и положил флажок. Пока
    флажка нет, CLI честно стоит в фазе «жду телевизор».
    """
    from torrcast.console import Progress
    from torrcast.stream import forget_playing, mark_playing, playing_flag

    out = tmp_path / "hls"
    out.mkdir(parents=True, exist_ok=True)
    forget_playing(out)
    monkeypatch.setattr(cli, "unit_active", lambda: True)
    config = Config(hls_dir=str(out))

    with pytest.raises(Exception, match="показ не начался"), Progress() as progress:
        AWAIT_PLAYING(config, progress, timeout=0.6)

    mark_playing(out)
    assert playing_flag(out).exists()
    with Progress() as progress:  # флажок на месте - ждать больше нечего
        AWAIT_PLAYING(config, progress, timeout=0.6)


def test_resume_keeps_asking_the_only_question_that_is_about_intent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Вопрос «Продолжить? [Y/n]» остаётся — он про намерение, а не про технику."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    asked = _answers(monkeypatch, "")

    assert cli.main(["моана", "2"]) == 0

    assert len(asked) == 1 and "Продолжить? [Y/n]" in asked[0]
    assert "ищу" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("answer", "start"),
    [
        ("", 2467.0),
        ("y", 2467.0),
        ("Y", 2467.0),
        ("да", 2467.0),
        ("д", 2467.0),
        ("n", 0.0),
        ("N", 0.0),
        ("н", 0.0),
        ("нет", 0.0),
        ("с", 0.0),
        ("s", 0.0),
        ("сначала", 0.0),
    ],
)
def test_the_prompt_promises_exactly_the_answers_that_are_taken(
    answer: str, start: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Надпись у вопроса и разбор ответа - одно и то же, иначе надпись врёт.

    Пара ``[Y/n]`` читается привычно: Enter и «да» продолжают с сохранённого места,
    «нет» играет тот же фильм с начала. Оба языка и оба регистра значат одно и то же.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    asked = _answers(monkeypatch, answer)

    assert cli.main(["моана", "2"]) == 0

    assert "Продолжить? [Y/n]" in asked[0], asked
    assert State.load().entries["movie:моана-2:2024"].pos == start


def test_a_bookmark_of_a_sequel_does_not_answer_which_picture_was_asked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Имя франшизы без номера зовёт первую часть, а не ту, на которой стоит закладка.

    Запись под запросом «моана» осталась от «Моаны 2»: её когда-то выбрали в меню, а в
    записи лежит текст запроса, а не имя картины. Продолжение по такой записи включало
    другое кино той же франшизы молча - и вопрос про картину не задавался вовсе.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана"),
    )
    state.save()
    asked = _answers(monkeypatch, "")  # Enter в меню - дефолт франшизы

    assert cli.main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert [q.split("[")[0].strip() for q in asked] == ["Что смотрим?"]
    assert "  1. Moana (2016)" in printed and "  2. Моана 2 (2024)" in printed
    assert "играю «Moana» (2016)" in printed, printed
    assert State.load().entries["movie:моана-2:2024"].pos == 2467.0, "закладка цела"


def test_the_bookmark_is_offered_inside_the_picture_that_was_chosen(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Закладка не выброшена: её предлагают той картине, которую человек выбрал.

    Сначала вопрос про картину, потом - про место в ней; вопросов по-прежнему два, и
    второй остаётся тем же самым «Продолжить?».
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана"),
    )
    state.save()
    asked = _answers(monkeypatch, "2", "")  # вторая картина меню, продолжить с места

    assert cli.main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert len(asked) == 2, asked
    assert asked[0].split("[")[0].strip() == "Что смотрим?", asked
    assert "«Моана 2» остановились на 0:41:07. Продолжить?" in asked[1], asked
    assert "играю «Моана 2»" in printed and "с 0:41:07" in printed, printed
    assert State.load().entries["movie:моана-2:2024"].pos == 2467.0, "продолжаем с места"


def test_a_legacy_record_of_a_film_written_as_a_series_behaves_as_a_film(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Старая ошибка разбора живёт в сохранённом состоянии: «Moana 2» записана ``tv`` с s1e1.

    Парсер починен, но запись живёт и позиция в ней настоящая — терять её нельзя.
    Одна серия в списке сериалом не считается: вопрос «Продолжить?» и ни слова про серии.
    """
    state = State()
    state.put(
        "tv:moana-2:2024",
        Entry(
            title="Moana 2",
            magnet="magnet:?xt=1",
            kind="tv",
            pos=2566.0,
            dur=5982.0,
            query="моана-2",
            season=1,
            episode=1,
            episodes=[[1, 1, 1]],
        ),
    )
    state.save()
    asked = _answers(monkeypatch, "")

    assert cli.main(["моана", "2"]) == 0

    printed = capsys.readouterr().out
    assert len(asked) == 1 and "Продолжить? [Y/n]" in asked[0]
    assert "s1e1" not in printed and "Серии" not in printed
    assert State.load().entries["tv:moana-2:2024"].pos == 2566.0, "позиция пользователя цела"


def test_prewarmed_torrents_are_dropped_when_the_show_never_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Обрыв до показа не оставляет прогретые раздачи в TorrServer.

    Прогрев под меню поднимает до :data:`~torrcast.cli.PREWARM` раздач ещё до первого
    вопроса. Любой выход мимо ``keep_only`` — Ctrl-C на «Что смотрим?», запуск без
    терминала, «годного релиза нет» — оставлял их жить в TorrServer: наш процесс умирает,
    а раздачи качаются в чужой RAM до перезапуска сервера.
    """
    dropped: list[str] = []
    added: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

        def drop(self, torrent_hash: str) -> bool:
            dropped.append(torrent_hash)
            return True

    monkeypatch.setattr(cli, "TorrServer", _Counting)
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": (_ for _ in ()).throw(KeyboardInterrupt)
    )

    assert cli.main(["моана"]) != 0, "Ctrl-C на вопросе - не показ"

    assert added, "прогрев под меню раздачи поднимает"
    assert len(dropped) == len(set(added)), "и все они убраны, раз показа не будет"


#: Раздачи «Moana» 2016 - первой живой части, в которую попадает Enter, - в порядке отбора.
SPARE_PICTURE = ("a" * 40, "b" * 40)


def _btih(magnet: str) -> str:
    """infoHash из magnet: по нему видно, какую именно раздачу подняли."""
    return magnet.partition("btih:")[2][:40]


def test_the_spare_release_warms_under_the_menu_not_after_the_first_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Под меню греется не только верх выбранной картины, но и её запасной релиз.

    Пока запасной поднимался только в отборе, брак верха стоил человеку полного подъёма
    второй раздачи - метаданные по DHT плюс ffprobe, - и всё это уже после вопроса, то
    есть на глазах. Пауза, пока меню читают, при этом простаивала.
    """
    added: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

    monkeypatch.setattr(cli, "TorrServer", _Counting)
    under_question: list[set[str]] = []

    def ask(prompt: str = "") -> str:
        if "Что смотрим?" in prompt:  # вопрос на экране, ответа ещё нет
            deadline = time.monotonic() + 5.0
            while len(added) < 3 and time.monotonic() < deadline:
                time.sleep(0.02)
            under_question.append({_btih(m) for m in added})
        return ""

    monkeypatch.setattr("builtins.input", ask)

    assert cli.main(["моана"]) == 0

    assert under_question, "меню про франшизу спросили"
    assert set(SPARE_PICTURE) <= under_question[0], "обе раздачи выбранной картины уже греются"


def test_the_unused_spare_leaves_torrserver_by_its_own_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Верх годен - запасной прибирается до старта показа, и прибирается ПО ХЭШУ.

    Своё убирается поимённо, а не «снести всё, что видно в TorrServer»: раздачи прогрева
    заведены с выключенным ``save_to_db``, в списке сервера их не видно вовсе, и чистка
    списком снесла бы чужое, не тронув наше.
    """
    added: list[str] = []
    dropped: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

        def drop(self, torrent_hash: str) -> bool:
            dropped.append(torrent_hash)
            return True

    monkeypatch.setattr(cli, "TorrServer", _Counting)
    _answers(monkeypatch, "", "")

    assert cli.main(["моана"]) == 0

    raised = {f"hash-{magnet[:30]}" for magnet in added}
    played = f"hash-magnet:?xt=urn:btih:{SPARE_PICTURE[0][:10]}"
    spare = f"hash-magnet:?xt=urn:btih:{SPARE_PICTURE[1][:10]}"
    assert spare in raised, "запасной релиз грелся"
    assert set(dropped) == raised - {played}, "лишнее убрано, и убрано по хэшам"
    assert played not in dropped, "играем то, что осталось"


def _started_film(monkeypatch: pytest.MonkeyPatch, pos: float = 2467.0) -> None:
    """Начатый фильм в состоянии — единственный вход на путь «Продолжить?»."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=pos, dur=5978.0, query="моана-2"),
    )
    state.save()
    monkeypatch.setattr(cli, "warm_file", lambda *a, **k: None)


def test_the_swarm_goes_up_while_the_question_is_still_unanswered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Раздача поднимается при ПЕЧАТИ вопроса, а не по ответу.

    Самая дорогая фаза продолжения — метаданные раздачи по DHT, и это секунды. Ровно
    столько же человек читает вопрос и тянется к клавише, поэтому подъём и уходит вперёд
    вопроса: к Enter'у метаданные чаще всего уже приехали. Ждать ответа, чтобы начать, —
    значит выбросить эту паузу целиком.
    """
    _started_film(monkeypatch)
    raised = threading.Event()

    class _Timed(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            raised.set()
            return f"hash-{magnet[:30]}"

    monkeypatch.setattr(cli, "TorrServer", _Timed)
    under_question: list[bool] = []

    def ask(prompt: str = "") -> str:
        under_question.append(raised.wait(5.0))  # вопрос на экране, ответа ещё нет
        return ""

    monkeypatch.setattr("builtins.input", ask)

    assert cli.main(["моана", "2"]) == 0
    assert under_question == [True], "раздача поднята, пока вопрос ещё не отвечен"


def test_the_position_warmer_dies_on_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Грелка позиции гаснет на Enter'е и ни секундой позже.

    Прогрев, доигрывающий после ответа, — это второй читатель того же места через
    TorrServer, и он отбирает у показа ровно ту полосу, ради которой затевался
    (:meth:`torrcast.cli._Resume.enough`). Смысл прогрева весь в секундах ДО ответа.
    """
    _started_film(monkeypatch)
    warming = threading.Event()
    alive_of: list[Any] = []

    def warm_file(source: str, at: float = 0.0, alive: Any = None, name: str = "") -> None:
        alive_of.append(alive)
        warming.set()

    monkeypatch.setattr(cli, "warm_file", warm_file)

    def ask(prompt: str = "") -> str:
        assert warming.wait(5.0), "грелка успевает встать под вопросом"
        return ""

    monkeypatch.setattr("builtins.input", ask)

    assert cli.main(["моана", "2"]) == 0
    assert alive_of and alive_of[0]() is False, "после ответа грелка себя считает мёртвой"


def test_a_failed_background_raise_is_not_a_failed_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Не поднялась раздача фоном — просто ждём как раньше, молча и не падая.

    Фоновый подъём — ускорение, а не источник правды: то же самое сделает сам показ в
    юните, только на своём времени. Ошибке отсюда нечего сказать человеку.
    """
    _started_film(monkeypatch)
    started: list[str] = []

    class _Dead(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            raise InfraError("TorrServer не отвечает")

    monkeypatch.setattr(cli, "TorrServer", _Dead)
    monkeypatch.setattr(cli, "start_play_unit", lambda key: started.append(key))
    _answers(monkeypatch, "")

    assert cli.main(["моана", "2"]) == 0
    assert started == ["movie:моана-2:2024"], "показ идёт своим ходом"
    assert "TorrServer" not in capsys.readouterr().out, "фоновая осечка человека не касается"


def test_a_run_that_never_starts_takes_its_torrent_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Показа не будет (``--dry``) — поднятая раздача убирается по ЕЁ хэшу.

    Раздача с ``save_to_db: false`` в списке TorrServer не видна, поэтому «снести всё из
    list» тут не годится вдвойне: и своё не найдёт, и чужое снесёт. Хэш известен ровно
    один — тот, что подняли сами.
    """
    _started_film(monkeypatch)
    added: list[str] = []
    dropped: list[str] = []
    raised = threading.Event()

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            raised.set()
            return f"hash-{magnet[:30]}"

        def drop(self, torrent_hash: str) -> bool:
            dropped.append(torrent_hash)
            return True

    monkeypatch.setattr(cli, "TorrServer", _Counting)

    def ask(prompt: str = "") -> str:
        raised.wait(5.0)
        return ""

    monkeypatch.setattr("builtins.input", ask)

    assert cli.main(["моана", "2", "--dry"]) == 0
    assert added == ["magnet:?xt=1"]
    assert dropped == ["hash-magnet:?xt=1"], "убрано ровно поднятое, по явному хэшу"


def test_a_dry_run_takes_even_the_chosen_torrent_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--dry`` с поиском убирает ВСЁ поднятое - и раздачу, которую «сыграли бы», тоже.

    Лишнее из прогрева убиралось всегда (:meth:`_Bench.keep_only`), а выбранная раздача
    оставалась жить в TorrServer до его перезапуска: с ``save_to_db: false`` в списке
    службы её не видно, и копилась она молча. Сухой прогон заведён ровно затем, чтобы
    следов не оставалось, - и сносить он обязан ровно своё, по явным хэшам.
    """
    added: list[str] = []
    dropped: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            torrent_hash = super().add(magnet)
            added.append(torrent_hash)
            return torrent_hash

        def drop(self, torrent_hash: str) -> bool:
            dropped.append(torrent_hash)
            return True

    monkeypatch.setattr(cli, "TorrServer", _Counting)
    _answers(monkeypatch, "")

    assert cli.main(["моана", "--dry"]) == 0

    # Чужие прогревы догорают в своих потоках и доносят свои сносы оттуда - дожидаемся,
    # но не дольше пяти секунд: на сломанном коде выбранная раздача не уходит никогда.
    deadline = time.monotonic() + 5.0
    while set(added) - set(dropped) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert added, "прогрев под меню раздачи поднимал"
    assert set(dropped) <= set(added), "снесено только своё, чужих хэшей тут нет"
    assert not set(added) - set(dropped), "убрано всё поднятое, выбранная - тоже"


def test_a_dry_run_names_the_chosen_file_not_the_request_echo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-302. Сухой прогон печатал ЭХО ЗАПРОСА (``series.want``), и дефект «сыграла
    серию „- 84" вместо s1e1» (сквозная нумерация против сезонной) им не виден ВООБЩЕ:
    числа по сериям, снятые всухую, были враньём. Теперь ``--dry`` называет, ЧТО он
    выбрал бы, - имя файла внутри раздачи.
    """

    class _SeriesProwlarr(_FakeProwlarr):
        def search(self, query: str) -> list[RawResult]:
            return [
                RawResult(
                    "Киберпанк: Бегущие по краю / Cyberpunk: Edgerunners (2022) "
                    "S01 WEB-DL 1080p x264 | D",
                    "e" * 40,
                    9 * GB,
                    55,
                )
            ]

    class _SeriesTorrServer(_FakeTorrServer):
        def wait_files(
            self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
        ) -> list[TorrFile]:
            return [TorrFile(i, f"Cyberpunk.S01E0{i + 1}.mkv", 2 * GB) for i in range(3)]

    monkeypatch.setattr(cli, "Prowlarr", _SeriesProwlarr)
    monkeypatch.setattr(cli, "TorrServer", _SeriesTorrServer)
    _answers(monkeypatch, "")

    assert cli.main(["киберпанк", "s1e3", "--dry"]) == 0

    said = capsys.readouterr().out
    assert "Cyberpunk.S01E03.mkv" in said, "сухой прогон называет ВЫБРАННЫЙ файл"
    assert "каста нет" in said


def test_an_instant_answer_is_no_worse_than_before(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enter нажали мгновенно — путь остаётся прежним: раздача та же, позиция цела.

    Подъём в этот момент ещё в пути, и ответ его не ждёт: показ поднимет ту же раздачу
    сам. Ускорение, которого не случилось, — это просто прежняя скорость.
    """
    _started_film(monkeypatch)
    started: list[str] = []

    class _Slow(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            time.sleep(0.3)  # человек успевает ответить раньше, чем раздача поднимется
            return f"hash-{magnet[:30]}"

    monkeypatch.setattr(cli, "TorrServer", _Slow)
    monkeypatch.setattr(cli, "start_play_unit", lambda key: started.append(key))
    _answers(monkeypatch, "")

    assert cli.main(["моана", "2"]) == 0
    assert started == ["movie:моана-2:2024"]
    kept = State.load().get("movie:моана-2:2024")
    assert kept is not None and kept.pos == 2467.0, "продолжаем с сохранённого места"


def test_two_pictures_under_one_name_reach_the_last_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-371. Строку про двусмысленность человек читает там же, где решение о картине.

    Развести пару одноимённых картин одного года отбору нечем: имя и год у них совпадают,
    и каталог сводит их в одну кучку. Значит слово остаётся за справкой, а место строки -
    последнее перед стартом, рядом с гейтом года: решение о КАРТИНЕ человек уносит с собой.
    """
    from torrcast.facts import Origin

    monkeypatch.setattr(
        cli,
        "origin",
        lambda *a, **k: Origin(title="Moana", year=2016, namesake="Моана (фильм, 2026)"),
    )
    _answers(monkeypatch, "1", "")

    assert cli.main(["моана"]) == 0

    printed = capsys.readouterr().out
    assert "под этим именем и годом картин две" in printed
    assert "«Моана (фильм, 2026)»" in printed


def _live_show(monkeypatch: pytest.MonkeyPatch) -> None:
    """Состояние живого показа: юнит поднят и держит раздачу «Моаны»."""
    state = State.load()
    state.put(
        OLD_KEY,
        Entry(title="Moana", magnet="magnet:?xt=urn:btih:" + "a" * 40, pos=128.0, torrent="a" * 40),
    )
    state.save()
    monkeypatch.setattr(cli, "unit_active", lambda *a, **k: True)


def test_a_second_cast_says_the_tv_is_busy_with_our_show(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-482. Один телевизор - один показ, и вторая команда говорит это словами зрителя.

    Прежде вторая ``cast`` на занятый телевизор вела себя как первая: ни строки о том, что
    на экране уже идёт фильм, ни слова о том, что выбор его оборвёт. Зритель узнавал об
    этом по погасшей картинке.
    """
    _live_show(monkeypatch)
    _answers(monkeypatch, "2", "")

    assert cli.main(["моана", "--new"]) == 0

    printed = capsys.readouterr().out
    assert "на телевизоре сейчас идёт «Moana»" in printed, printed
    assert "0:02:08" in printed, "видно и то, докуда досмотрели"
    assert "этот показ прервётся" in printed, printed


def test_the_menu_prewarm_stands_aside_while_our_show_is_on_air(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-482. Пока идёт показ, прогрев под меню не поднимает ни одной раздачи.

    Замер 10-08: рядом с живым показом шла вторая ``cast``, и её прогрев тянул из роя
    чужие раздачи, писал их на тот же диск и читал ту же сеть - про показ он не знал
    ничего и не притормаживал. Показ первичен: раздумья зрителя оплачивает скорость
    нашего меню, а не его картинка.
    """
    added: list[str] = []

    class _Counting(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            added.append(magnet)
            return f"hash-{magnet[:30]}"

    monkeypatch.setattr(cli, "TorrServer", _Counting)
    _live_show(monkeypatch)

    under_question: list[int] = []

    def ask(prompt: str = "") -> str:
        if "Что смотрим?" in prompt:  # вопрос на экране, ответа ещё нет
            time.sleep(0.5)  # прогрев успел бы поднять три раздачи вдесятеро быстрее
            under_question.append(len(added))
        return ""

    monkeypatch.setattr("builtins.input", ask)

    assert cli.main(["моана", "--new"]) == 0

    assert under_question == [0], "под меню живого показа не поднято ни одной раздачи"


def test_a_hand_named_release_weighs_the_same_on_both_early_exits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Один и тот же ``--release N`` не может зависеть от того, совпал ли текст запроса.

    Ранних выхода по закладке два: один находит запись по тексту запроса, другой
    предлагает её внутри выбранной картины. Названный руками релиз на второй не заходит -
    раздачу там выбирает человек, - и на первый теперь тоже: иначе `cast моана 2` с
    флагом играл записанную раздачу, выбросив флаг молча, а `cast моана` с тем же флагом
    его уважал.
    """
    played = []
    for saved_query in ("моана-2", "моана"):  # текст запроса совпал с записью - и нет
        state = State()
        state.put(
            "movie:моана-2:2024",
            Entry(
                title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query=saved_query
            ),
        )
        state.save()
        _answers(monkeypatch, "2", "")  # вторая картина меню, если о ней спросят

        assert cli.main(["моана", "2", "--release", "2"]) == 0

        capsys.readouterr()
        played.append(State.load().entries["movie:моана-2:2024"].magnet[:24])

    assert played[0] == played[1], "флаг решает исход одинаково на обоих путях"
    assert played[0] == "magnet:?xt=urn:btih:dddd", played  # названный релиз, не записанный


def test_a_hand_named_release_says_out_loud_that_it_drops_the_bookmark(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Названный релиз играется с начала - и сохранённое место теряется НЕ молча.

    Стартовая запись показа ложится под тот же ключ картины, то есть 41:07 после такого
    запуска не восстановить ниоткуда. `--release N` человек набирает про раздачу, а не
    про закладку, и узнать о её пропаже он обязан строкой до старта.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    _answers(monkeypatch, "2", "")

    assert cli.main(["моана", "2", "--release", "2"]) == 0

    said = capsys.readouterr().out
    assert "не поднимаю" in said, said
    assert "41:07" in said, "место названо тем же временем, что и в вопросе «Продолжить?»"
    assert State.load().entries["movie:моана-2:2024"].pos == 0.0, "играли с начала"


def test_continuing_without_a_flag_keeps_the_bookmark_and_stays_silent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Обычный `cast моана 2` по-прежнему продолжает начатое, и лишней строки нет.

    Условие раннего выхода выросло на ``not args.pinned``, и цена ошибки тут - потерянное
    место просмотра у того, кто никаких флагов не набирал.
    """
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    asked = _answers(monkeypatch, "")  # Enter на «Продолжить?»

    assert cli.main(["моана", "2"]) == 0

    said = capsys.readouterr().out
    assert any("Продолжить?" in prompt for prompt in asked), asked
    assert "не поднимаю" not in said, said
    kept = State.load().entries["movie:моана-2:2024"]
    assert kept.pos == 2467.0, "место осталось на 41:07"
    assert kept.magnet == "magnet:?xt=1", "играли записанную раздачу, а не выбранную заново"
