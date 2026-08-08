"""Счастливый путь: фильм и озвучка, больше ничего.

Проверяется дословное требование к продукту: «не хочу видеть какие там файлы, хочу
выбрать фильм и озвучку». Значит на обязательном пути нет ни таблицы релизов, ни списка
файлов, ни строк про серии у фильма, а вопросов ровно два — и оба пропускаются, когда
выбор единственный.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast import cli
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


class _FakeTorrServer:
    """Раздача в объёме подготовки релиза: hash, файлы, URL потока."""

    def __init__(self, url: str) -> None:
        self.url = url

    def add(self, magnet: str) -> str:
        return f"hash-{magnet[:30]}"

    def wait_files(self, torrent_hash: str, timeout: float = 60.0) -> list[TorrFile]:
        return [
            TorrFile(0, "Moana/Moana.2016.1080p.mkv", 5 * GB),
            TorrFile(1, "Moana/Moana.sample.mkv", 30 * 1024**2),
            TorrFile(2, "Moana/cover.jpg", 1024),
        ]

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> None:
        pass


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

    Enter приводит в самую живую картину, а не в первую по хронологии:
    у «Моаны 2» верх отбора собрал 140 сидов, у «Moana» 2016 — 22.
    """
    _answers(monkeypatch, "", "")

    assert cli.main(["моана"]) == 0
    printed = capsys.readouterr().out
    assert "  1. Moana (2016)\n  2. Моана 2 (2024)" in printed, "список остался хронологией"
    assert "играю «Моана 2» (2024)" in printed


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
    assert "вслепую не выбираю" in printed.err and "Моана 2" in printed.err
    kept = State.load().get(OLD_KEY)
    assert kept is not None and kept.pos == 2467.0, "сохранённую позицию не трогаем никогда"


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


def test_releases_prints_the_old_table_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    """`cast releases <запрос>` — та самая таблица, но только по явной просьбе."""
    assert cli.main(["releases", "моана"]) == 0

    printed = capsys.readouterr().out
    assert "Релизы:" in printed and "Качество" in printed
    assert "Moana (2016)" in printed and "Моана 2 (2024)" in printed
    assert "играю" not in printed, "releases ничего не запускает"


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
    """Вопрос «Продолжить? [Да/сначала]» остаётся — он про намерение, а не про технику."""
    state = State()
    state.put(
        "movie:моана-2:2024",
        Entry(title="Моана 2", magnet="magnet:?xt=1", pos=2467.0, dur=5978.0, query="моана-2"),
    )
    state.save()
    asked = _answers(monkeypatch, "")

    assert cli.main(["моана", "2"]) == 0

    assert len(asked) == 1 and "Продолжить? [Да/сначала]" in asked[0]
    assert "ищу" not in capsys.readouterr().out


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
    assert len(asked) == 1 and "Продолжить? [Да/сначала]" in asked[0]
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

        def drop(self, torrent_hash: str) -> None:
            dropped.append(torrent_hash)

    monkeypatch.setattr(cli, "TorrServer", _Counting)
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": (_ for _ in ()).throw(KeyboardInterrupt)
    )

    assert cli.main(["моана"]) != 0, "Ctrl-C на вопросе - не показ"

    assert added, "прогрев под меню раздачи поднимает"
    assert len(dropped) == len(set(added)), "и все они убраны, раз показа не будет"
