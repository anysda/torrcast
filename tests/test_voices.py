"""Озвучка: дефолт без вопроса, флаг ``--voice`` и память на картину.

Меню озвучки со счастливого пути убрано: «самая нормальная» дорожка выбирается сама,
а выбор флагом запоминается за фильмом или сериалом.

⚠️ Дорожки в тестах — **живые**, снятые с настоящих раздач (`scripts/voicedump.py`).
Выдумывать их нельзя: вся эвристика держится на том, как студии на самом деле подписывают
дорожки, а подписывают они их куда причудливее, чем кажется из головы («Дубляж для
слабовидящих» сразу за нормальным дубляжом, украинский и казахский дубляж с тем же
русским словом «Дубляж» в заголовке, «[TVShows][MVO]», «DUB-Blu-ray CEE», «AVO-Сербин»).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast import cli
from torrcast.search import RawResult
from torrcast.state import Config, Entry, State, save_config
from torrcast.stream import AudioTrack, Media, TorrFile

GB = 1024**3
KEY = "movie:моана-2:2024"

#: «Тачки 3», WEB-DL 1080p. Ловушка тут не одна, а две: дорожка 2 - тифлокомментарий
#: («Дубляж для слабовидящих»), а 3 и 4 - чужие дубляжи, у которых в заголовке стоит
#: то же русское слово «Дубляж», и различает их только тег языка.
CARS = (
    AudioTrack(0, "rus", "Дубляж", "ac3", 6),
    AudioTrack(1, "rus", "Дубляж для слабовидящих", "aac", 2),
    AudioTrack(2, "ukr", "Дубляж", "ac3", 6),
    AudioTrack(3, "kaz", "Дубляж", "aac", 2),
    AudioTrack(4, "eng", "Оригинал", "ac3", 6),
)
#: «Моана 2», BDRip 720p: три дубляжа, пять многоголосых и оригинал.
MOANA2 = (
    AudioTrack(0, "rus", "Дубляж. (MovieDalen)", "ac3", 2),
    AudioTrack(1, "rus", "Дубляж. (Red Head Soundn)", "ac3", 6),
    AudioTrack(2, "rus", "Дубляж. (Jaskier)", "ac3", 6),
    AudioTrack(3, "rus", "MVO. (Jaskier)", "ac3", 6),
    AudioTrack(4, "rus", "MVO (TVShows)", "ac3", 6),
    AudioTrack(5, "rus", "MVO (LostFilm)", "ac3", 2),
    AudioTrack(6, "rus", "MVO (HDRezka Studio)", "ac3", 2),
    AudioTrack(7, "rus", "MVO (1win Studio)", "ac3", 2),
    AudioTrack(8, "eng", "Original", "dts", 6),
)
#: «Интерстеллар», IMAX 720p: дубляж, чужой дубляж, многоголосый и три авторских.
INTERSTELLAR = (
    AudioTrack(0, "rus", "DUB-Blu-ray CEE", "ac3", 6),
    AudioTrack(1, "ukr", "DUB-Blu-ray CEE", "ac3", 6),
    AudioTrack(2, "rus", "MVO-студия «Омикрон»", "ac3", 6),
    AudioTrack(3, "rus", "AVO-Сербин", "ac3", 6),
    AudioTrack(4, "rus", "AVO-Живов", "ac3", 6),
    AudioTrack(5, "rus", "VO-Есарев", "ac3", 6),
    AudioTrack(6, "eng", "Original", "ac3", 6),
)
#: «Киберпанк: Бегущие по краю», s1e1: русский многоголосый и японский оригинал без
#: заголовка вовсе. Дубляжа у сериала нет - дефолт обязан спуститься на ступень ниже.
CYBERPUNK = (
    AudioTrack(0, "rus", "[TVShows][MVO]", "ac3", 2),
    AudioTrack(1, "jpn", None, "eac3", 6),
)
#: «Матрица», HDTVRip-AVC: заголовки с техническим хвостом через дробь.
MATRIX = (
    AudioTrack(0, "rus", "DUB (Rus) / AC3 / 6 ch / 384 kbps / 48 kHz", "ac3", 6),
    AudioTrack(1, "rus", "AVO Визгунов (Rus) / AC3 / 2 ch / 192 kbps / 48 kHz", "ac3", 2),
    AudioTrack(2, "eng", "Original (Eng) / AC3 / 6 ch / 384 kbps / 48 kHz", "ac3", 6),
)


@pytest.mark.parametrize(
    ("tracks", "want", "why"),
    [
        (CARS, 0, "русский дубляж, а не тифлокомментарий и не украинский с казахским"),
        (MOANA2, 0, "первый из трёх дубляжей - порядок внутри ступени авторский"),
        (INTERSTELLAR, 0, "дубляж выше многоголосого и авторских"),
        (CYBERPUNK, 0, "дубляжа нет - берём русский многоголосый, а не японский оригинал"),
        (MATRIX, 0, "технический хвост заголовку не мешает"),
        (INTERSTELLAR[1:], 1, "без дубляжа - русский многоголосый (ukr-дубляж не в счёт)"),
        (INTERSTELLAR[3:], 0, "остались авторские - берём первый русский, не оригинал"),
        (CARS[1:], 3, "остались тифлокомментарий и чужие дубляжи - оригинал лучше всех"),
        (CARS[1:4], 1, "и даже без оригинала украинский дубляж выше тифлокомментария"),
        ((), 0, "дорожек нет - говорить не о чем"),
    ],
)
def test_the_sanest_voice_is_picked_by_the_ladder(
    tracks: tuple[AudioTrack, ...], want: int, why: str
) -> None:
    """Лестница дефолта: русский дубляж → русский многоголосый → прочий русский →
    оригинал → чужой дубляж, служебные дорожки — ниже всех.
    """
    expected = tracks[want].index if tracks else 0
    assert Media(tracks=tracks).default_track() == expected, why


def test_the_language_tag_beats_the_title() -> None:
    """«Дубляж» с тегом ``kaz`` — казахская дорожка, как её ни подпиши (живой «Тачки 3»)."""
    assert [t.is_russian for t in CARS] == [True, True, False, False, False]
    assert [t.is_russian for t in CYBERPUNK] == [True, False]


def test_the_label_drops_the_technical_tail() -> None:
    """Подпись — она же ключ памяти: битрейт и частота в ней только мешают."""
    assert MATRIX[0].label == "rus · DUB (Rus)"
    assert MOANA2[0].label == "rus · Дубляж. (MovieDalen)"
    assert CYBERPUNK[1].label == "jpn"


def test_a_remembered_voice_is_found_by_label_not_by_number() -> None:
    """Память переживает смену релиза: ищем подпись, а не номер дорожки."""
    media = Media(tracks=MOANA2)
    assert media.find_voice("rus · MVO (LostFilm)") == 5
    assert media.find_voice("RUS · mvo (lostfilm)") == 5, "регистр значения не имеет"
    assert media.find_voice("rus · MVO (Кубик в кубе)") is None
    assert media.find_voice("") is None


# --- память на картину: сквозь настоящий cli ------------------------------------------

FOUND = [
    RawResult("Моана 2 / Moana 2 (2024) WEB-DL 1080p | D, P", "c" * 40, 3 * GB, 140),
    RawResult("Moana 2 (2024) 1080p BRRip 5.1 x264 -YTS", "d" * 40, 2 * GB, 121),
]


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Окружение без Prowlarr, TorrServer и systemd — но с настоящим выбором озвучки."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    save_config(Config(tv="mock", prowlarr_apikey="ключ", hls_dir=str(tmp_path / "hls")))
    monkeypatch.setattr(cli, "Prowlarr", _FakeProwlarr)
    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(cli, "probe", lambda url, timeout=90.0, alive=None: Media(5978.0, MOANA2, "h264", 1080))
    monkeypatch.setattr(cli, "start_play_unit", lambda key: None)
    monkeypatch.setattr(cli, "stop_play_unit", lambda: None)
    monkeypatch.setattr(cli, "_await_playing", lambda config, progress, timeout=120.0: None)


class _FakeProwlarr:
    def __init__(self, url: str, apikey: str) -> None:
        self.url = url

    def search(self, query: str) -> list[RawResult]:
        return list(FOUND)


class _FakeTorrServer:
    def __init__(self, url: str) -> None:
        self.url = url

    def add(self, magnet: str) -> str:
        return f"hash-{magnet[:30]}"

    def wait_files(self, torrent_hash: str, timeout: float = 60.0) -> list[TorrFile]:
        return [TorrFile(0, "Moana.2.2024.1080p.mkv", 3 * GB)]

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> None:
        pass


def _answers(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    asked: list[str] = []
    queue = iter(replies)

    def ask(prompt: str = "") -> str:
        asked.append(prompt)
        return next(queue, "")

    monkeypatch.setattr("builtins.input", ask)
    return asked


def test_the_default_voice_is_named_in_the_launch_line_and_not_remembered(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Автовыбор говорит, что взял, но памяти не пишет: её пишет только человек."""
    _answers(monkeypatch)

    assert cli.main(["моана", "2"]) == 0

    assert "rus · Дубляж. (MovieDalen)" in capsys.readouterr().out
    saved = State.load().entries[KEY]
    assert (saved.audio, saved.voice) == (0, ""), "автовыбор память не занимает"


def test_the_flag_picks_a_track_and_remembers_it_for_this_picture(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--voice N`` — явный выбор: играем его и запоминаем за картиной."""
    _answers(monkeypatch)

    assert cli.main(["моана", "2", "--voice", "6"]) == 0

    assert "rus · MVO (LostFilm)" in capsys.readouterr().out
    saved = State.load().entries[KEY]
    assert (saved.audio, saved.voice) == (5, "rus · MVO (LostFilm)")


def test_the_next_run_takes_the_remembered_voice_without_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Следующий ``cast <тот же фильм>`` играет запомненной озвучкой и молчит про меню."""
    _answers(monkeypatch)
    assert cli.main(["моана", "2", "--voice", "6"]) == 0
    capsys.readouterr()

    asked = _answers(monkeypatch)
    assert cli.main(["моана", "2", "--new"]) == 0

    printed = capsys.readouterr().out
    assert asked == [], "вопросов нет: и картина одна, и озвучка выбрана в прошлый раз"
    assert "rus · MVO (LostFilm)" in printed and "Озвучка:" not in printed
    assert State.load().entries[KEY].audio == 5


def test_a_new_flag_overwrites_the_memory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Явный флаг сильнее памяти и переписывает её."""
    _answers(monkeypatch)
    assert cli.main(["моана", "2", "--voice", "6"]) == 0
    assert cli.main(["моана", "2", "--new", "--voice", "3"]) == 0
    capsys.readouterr()

    saved = State.load().entries[KEY]
    assert (saved.audio, saved.voice) == (2, "rus · Дубляж. (Jaskier)")


def test_a_remembered_voice_missing_from_the_release_is_said_out_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Озвучки нет в этом релизе — говорим и играем обычную, но выбор не забываем.

    Память живёт на картину, а релиз временный: сегодня верх отбора один, завтра другой.
    Стирать выбор пользователя из-за раздачи, которая до него не доехала, — та же
    молчаливая подмена, только наоборот.
    """
    state = State()
    state.put(KEY, Entry(title="Моана 2", magnet="m", query="моана-2", voice="rus · Кубик в кубе"))
    state.save()
    _answers(monkeypatch)

    assert cli.main(["моана", "2", "--new"]) == 0

    printed = capsys.readouterr().out
    assert "озвучки «rus · Кубик в кубе» в этом релизе нет - беру обычную" in printed
    assert "rus · Дубляж. (MovieDalen)" in printed
    saved = State.load().entries[KEY]
    assert (saved.audio, saved.voice) == (0, "rus · Кубик в кубе"), "память цела"


def test_a_wrong_number_is_a_polite_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Дорожки с таким номером нет — честная строка и код «не нашли», а не показ."""
    monkeypatch.setattr(cli, "start_play_unit", lambda key: pytest.fail("вслепую не кастим"))
    _answers(monkeypatch)

    assert cli.main(["моана", "2", "--voice", "42"]) == 1


def test_the_menu_comes_only_with_a_bare_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--voice`` без номера — то самое меню, убранное со счастливого пути."""
    asked = _answers(monkeypatch, "5")

    assert cli.main(["моана", "2", "--voice"]) == 0

    printed = capsys.readouterr().out
    assert "Озвучка:" in printed and "  1. rus · Дубляж. (MovieDalen)   [дефолт]" in printed
    assert len(asked) == 1 and "Озвучка?" in asked[0]
    saved = State.load().entries[KEY]
    assert (saved.audio, saved.voice) == (4, "rus · MVO (TVShows)")


def test_the_voices_command_lists_and_exits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``cast voices <запрос>`` — список с пометками, и никакого показа."""
    state = State()
    state.put(KEY, Entry(title="Моана 2", magnet="m", query="моана-2", voice="rus · MVO (TVShows)"))
    state.save()
    monkeypatch.setattr(cli, "start_play_unit", lambda key: pytest.fail("voices ничего не играет"))

    assert cli.main(["voices", "моана 2"]) == 0

    printed = capsys.readouterr().out
    assert "  1. rus · Дубляж. (MovieDalen)   [дефолт]" in printed
    assert "  5. rus · MVO (TVShows)   [запомнено]" in printed
    assert "cast <запрос> --voice N" in printed
    assert "играю" not in printed


def test_a_record_with_nothing_to_continue_does_not_wake_the_swarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--voice`` у записи, которую продолжать нечем, идёт обычным путём.

    Перечитывать дорожки по записи состояния имеет смысл только там, где по ней и пойдёт
    показ. Иначе флаг поднимал в TorrServer раздачу, которую никто играть не собирался,
    и падал на её магните — ловилось живым прогоном.
    """
    state = State()
    state.put(KEY, Entry(title="Моана 2", magnet="мёртвый магнит", query="моана-2"))
    state.save()

    class _Strict(_FakeTorrServer):
        def add(self, magnet: str) -> str:
            if magnet == "мёртвый магнит":
                pytest.fail("раздачу, которую никто не играет, поднимать незачем")
            return super().add(magnet)

    monkeypatch.setattr(cli, "TorrServer", _Strict)
    _answers(monkeypatch)

    assert cli.main(["моана", "2", "--voice", "6"]) == 0

    assert State.load().entries[KEY].voice == "rus · MVO (LostFilm)"


def test_a_series_remembers_the_voice_for_the_whole_show(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """У сериала память общая на сериал, а не на серию.

    Она и лежит в одной записи на всю раздачу: выбор переезжает на следующую серию сам,
    вместе с релизом и списком серий. ``--voice`` тут перечитывает дорожки раздачи —
    иначе на этом пути номеров и подписей взять неоткуда: поток никто не открывал.
    """
    key = "tv:киберпанк:2022"
    state = State()
    state.put(
        key,
        Entry(
            title="Киберпанк",
            magnet="m",
            kind="tv",
            query="киберпанк",
            season=1,
            episode=2,
            episodes=[[1, 1, 0], [1, 2, 1], [1, 3, 2]],
        ),
    )
    state.save()
    _answers(monkeypatch)

    assert cli.main(["киберпанк", "--voice", "5"]) == 0

    saved = State.load().entries[key]
    assert (saved.audio, saved.voice) == (4, "rus · MVO (TVShows)")
    assert saved.advance().voice == saved.voice, "следующая серия наследует выбор сериала"

    capsys.readouterr()
    asked = _answers(monkeypatch)
    assert cli.main(["киберпанк"]) == 0
    assert asked == [], "повторный запуск ничего не спрашивает"
    assert "rus · MVO (TVShows)" in capsys.readouterr().out


def test_the_old_flag_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--audio N`` — прежнее имя того же флага; ломать его незачем."""
    _answers(monkeypatch)

    assert cli.main(["моана", "2", "--audio", "6"]) == 0

    assert State.load().entries[KEY].voice == "rus · MVO (LostFilm)"
