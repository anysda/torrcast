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
from typing import ClassVar

import pytest

from torrcast import InfraError, cli
from torrcast.console import Progress
from torrcast.search import RawResult
from torrcast.state import Config, Entry, State, save_config
from torrcast.stream import (
    STEP_FOREIGN,
    STEP_RU_PLAIN,
    STEP_SERVICE,
    STUDIOS,
    VOICE_KINDS,
    AudioTrack,
    Media,
    TorrFile,
    voice_order,
)
from torrcast.usecases import playback

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
#: «Барби», WEB-DL 1080p. Ни одна русская дорожка не названа видом перевода - только
#: студией, и лестница по заголовку тут слепа целиком.
BARBIE = (
    AudioTrack(0, "rus", "Bravo Records Georgia", "ac3", 6),
    AudioTrack(1, "rus", "LostFilm", "ac3", 6),
    AudioTrack(2, "rus", "TVShows", "ac3", 6),
    AudioTrack(3, "eng", "Original", "ac3", 6),
)
#: «Головоломка»: дубляж подписан студией и лежит НЕ первым - порядок в файле его не
#: спасает, ступень спасает.
INSIDEOUT = (
    AudioTrack(0, "rus", "LostFilm", "ac3", 6),
    AudioTrack(1, "rus", "HDrezka Studio", "ac3", 6),
    AudioTrack(2, "rus", "MovieDalen", "ac3", 6),
    AudioTrack(3, "eng", "Original", "dts", 6),
)
#: «Криминальное чтиво»: дубляж Невафильма против двухголосого «Кубик в Кубе».
PULP = (
    AudioTrack(0, "rus", "Кубик в Кубе", "ac3", 2),
    AudioTrack(1, "rus", "Nevafilm", "ac3", 6),
    AudioTrack(2, "eng", "Original", "ac3", 6),
)
#: «Твоё имя»: у аниме студия в заголовке - вообще единственная подпись, какая бывает.
YOURNAME = (
    AudioTrack(0, "rus", "AlexFilm", "aac", 2),
    AudioTrack(1, "rus", "SHIZA Project", "aac", 2),
    AudioTrack(2, "rus", "Timecraft", "aac", 6),
    AudioTrack(3, "jpn", "Original", "flac", 2),
)
#: Дубляж, написанный не словом «дубляж»: так подписывают лицензионную дорожку.
DUBBED_WORDS = (
    AudioTrack(0, "rus", "MVO (TVShows)", "ac3", 6),
    AudioTrack(1, "rus", "Dubbed", "ac3", 6),
    AudioTrack(2, "rus", "Dubbing", "ac3", 6),
    AudioTrack(3, "rus", "Лицензия", "ac3", 6),
    AudioTrack(4, "rus", "Полное дублирование", "ac3", 6),
    AudioTrack(5, "rus", "iTunes", "ac3", 6),
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
        (BARBIE, 1, "студия читается как ступень: LostFilm выше незнакомой студии"),
        (INSIDEOUT, 2, "дубляж студии берётся третьим по счёту, а не первым по порядку"),
        (PULP, 1, "дубляж Невафильма выше двухголосого, хоть и лежит вторым"),
        (YOURNAME, 2, "дубляж студии выше двух многоголосых, стоящих раньше него"),
        (DUBBED_WORDS, 1, "«Dubbed» - это дубляж, и он выше многоголосого"),
        (DUBBED_WORDS[3:], 0, "«Лицензия», «Полное дублирование» и «iTunes» - тоже дубляж"),
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


def test_a_studio_signature_reads_as_a_rung_of_the_ladder() -> None:
    """Подпись студией - тот же вид перевода, только сказанный именем студии."""
    assert [t.kind for t in BARBIE] == ["", "многоголосый", "многоголосый", ""]
    assert [t.kind for t in INSIDEOUT] == ["многоголосый", "многоголосый", "дубляж", ""]
    # Кубик в Кубе вслух остаётся двухголосым, хотя судим мы их по многоголосой ступени.
    assert [t.kind for t in PULP] == ["двухголосый", "дубляж", ""]
    assert [t.kind for t in YOURNAME] == ["многоголосый", "многоголосый", "дубляж", ""]


def test_the_title_beats_the_studio_table() -> None:
    """Что дорожка написала про себя, точнее того, что мы знаем про студию вообще.

    Jaskier делает и дубляж, и многоголосый закадровый, и в «Моане 2» лежат обе его
    дорожки. Таблица студий тут второй голос, а не первый.
    """
    assert MOANA2[2].kind == "дубляж" and MOANA2[3].kind == "многоголосый"


def test_an_unknown_studio_does_not_break_the_choice() -> None:
    """Таблица студий заведомо протухает: незнакомая студия не поднимает и не роняет.

    «Bravo Records Georgia» в таблице нет и не будет - таких имён в раздачах бесконечно.
    Дорожка остаётся русской без метки, то есть ровно там, где стояла до таблицы.
    """
    unknown = AudioTrack(0, "rus", "Bravo Records Georgia")
    assert unknown.studio is None and unknown.kind == ""
    assert unknown.step == STEP_RU_PLAIN
    assert unknown.is_russian, "тег языка её русской и оставляет"
    assert Media(tracks=(unknown,)).default_track() == 0, "одна дорожка - она и играет"


def test_the_studio_table_never_beats_the_language_tag_or_lifts_a_service_track() -> None:
    """Два ограждения таблицы: тег языка сильнее заголовка, тифлокомментарий - внизу."""
    foreign = AudioTrack(0, "ukr", "Дубляж (LostFilm)")
    assert not foreign.is_russian and foreign.step == STEP_FOREIGN
    service = AudioTrack(1, "rus", "Дубляж для слабовидящих (Мосфильм)")
    assert service.step == STEP_SERVICE


def test_studio_fame_ranks_studios_within_a_step() -> None:
    """Ранжир крутости разводит студии внутри ступени; ступени из лестницы не смешиваются.

    fame работает ТОЛЬКО внутри ступени: дубляж всегда выше многоголосого,
    даже если у многоголосого fame=100.
    """
    # ступени в таблице - только иззвестных (:data:`VOICE_KINDS`)
    assert {s.kind for s in STUDIOS.values()} <= set(VOICE_KINDS), "ступени только из лестницы"
    # AniDub вредоносный и fame отрицательный; Кубик в Кубе - положительный
    assert STUDIOS["anidub"].fame < 0
    assert STUDIOS["кубик в кубе"].fame > 0
    # равная ступень, разный вес - порядок по весу
    assert voice_order(MOANA2[4]) < voice_order(MOANA2[5]), (
        "TVShows (0) выше LostFilm (0) только по индексу"
    )
    # дубляж не пробивается fame многоголосого - лестница сильнее
    dub = AudioTrack(0, "rus", "Дубляж")
    mvo_high_fame = AudioTrack(1, "rus", "Кубик в Кубе")
    assert voice_order(dub) < voice_order(mvo_high_fame), (
        "дубляж всегда выше, даже если у многоголосого fame=10"
    )


#: «Фарго» (sезон без дубляжа): Кубик в Кубе против LostFilm, два многоголосых.
#: Дорожки реальные - так подписывают сериальные раздачи.
FARGO = (
    AudioTrack(0, "rus", "MVO (LostFilm)", "ac3", 2),
    AudioTrack(1, "rus", "Кубик в Кубе", "ac3", 2),
    AudioTrack(2, "eng", "Original", "ac3", 6),
)


def test_kubik_beats_lostfilm() -> None:
    """Кубик в Кубе побеждает LostFilm как в меню, так и в дефолте.

    Кубик двухголосый, и вслух он так и называется, но судят его по многоголосой
    ступени (``ranks``), а внутри неё решает fame: у Кубика он положительный,
    у LostFilm - нулевой.
    """
    assert STUDIOS["кубик в кубе"].kind == "двухголосый", "вслух - что есть на самом деле"
    assert STUDIOS["кубик в кубе"].ranks == "многоголосый", "судим по ступени выше"
    assert voice_order(FARGO[1]) < voice_order(FARGO[0]), "Кубик левее LostFilm в очереди"
    assert Media(tracks=FARGO).default_track() == FARGO[1].index, "Кубик берётся дефолтом"


#: «Фрирен» (s1e1): AniLibria и AniDub в одной раздаче; оригинал японский.
#: AniDub встраивает 21 с рекламы - должна победить AniLibria.
FRIEREN = (
    AudioTrack(0, "rus", "AniLibria", "aac", 2),
    AudioTrack(1, "rus", "AniDub", "aac", 2),
    AudioTrack(2, "jpn", "Original", "flac", 2),
)
#: «Фрирен»: релиз без AniLibria - только AniDub и оригинал.
FRIEREN_ANIDUB_ONLY = (
    AudioTrack(0, "rus", "AniDub", "aac", 2),
    AudioTrack(1, "jpn", "Original", "flac", 2),
)


def test_anilibria_beats_anidub() -> None:
    """При живой AniLibria дефолт на «Фрирене» - не AniDub.

    AniDub встраивает рекламу прямо в файл (замерено: s1e1 у AniLibria 26:00,
    у AniDub 26:21 - лишние 21 с), и fame у них отрицательный.
    Если AniDub - единственный русский вариант, всё равно берётся он.
    """
    assert STUDIOS["anidub"].fame < 0
    assert Media(tracks=FRIEREN).default_track() == FRIEREN[0].index, "AniLibria, не AniDub"
    assert Media(tracks=FRIEREN_ANIDUB_ONLY).default_track() == FRIEREN_ANIDUB_ONLY[0].index, (
        "AniDub единственный русский - берётся он, реклама лучше японского"
    )


def test_voice_note_explains_non_default_choice() -> None:
    """Если дефолт - не дубляж, voice_note честно объясняет почему взяла именно эту.

    Например, Кубик в Кубе в Фарго: дубляжа нет, берётся лучшая доступная студия.
    """
    note = cli.voice_note(Media(tracks=FARGO), Media(tracks=FARGO).default_track())
    assert "Кубик в Кубе" in note, "студия называется"
    assert "двухголосый" in note, "вид перевода называется честно"


def test_the_note_explains_the_choice_only_when_there_was_one() -> None:
    """Строка про выбор: сколько было русских и что взяли; выбора не было - молчим."""
    assert cli.voice_note(Media(tracks=BARBIE), 1) == "дорожек rus 3, беру многоголосый (LostFilm)"
    assert cli.voice_note(Media(tracks=INSIDEOUT), 2) == "дорожек rus 3, беру дубляж (MovieDalen)"
    assert cli.voice_note(Media(tracks=PULP), 1) == "дорожек rus 2, беру дубляж (Невафильм)"
    assert cli.voice_note(Media(tracks=CYBERPUNK), 0) == "", "русская одна - выбора не было"
    assert cli.voice_note(Media(tracks=()), 0) == "", "дорожек нет - и говорить не о чем"
    assert "LostFilm" not in cli.voice_note(Media(tracks=INSIDEOUT), 2), "список студий не печатаем"


def test_the_note_names_why_the_ladder_was_beaten_by_type() -> None:
    """🔴 TC-242. Дефолт сошёл с лестницы по типу - строка называет причину.

    «Беру двухголосый» рядом с живым многоголосым читается как противоречие лестнице:
    двухголосый на ней НИЖЕ. Причина одна - студию судят по отборной ступени
    (``Studio.ranks``), и она называется коротким хвостом в той же строке. Нет
    расхождения - нет и хвоста.
    """
    media = Media(tracks=FARGO)
    assert cli.voice_note(media, media.default_track()) == (
        "дорожек rus 2, беру двухголосый (Кубик в Кубе) - эта студия у нас на уровне «многоголосый»"
    )
    # Дорожка сама назвалась многоголосой - отборная ступень совпала с произносимой,
    # и причины называть нечего.
    named = (
        AudioTrack(0, "rus", "MVO (Кубик в Кубе)", "ac3", 2),
        AudioTrack(1, "rus", "MVO (LostFilm)", "ac3", 2),
        AudioTrack(2, "eng", "Original", "ac3", 6),
    )
    assert cli.voice_note(Media(tracks=named), 0) == (
        "дорожек rus 2, беру многоголосый (Кубик в Кубе)"
    )


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
    _FakeTorrServer.added, _FakeTorrServer.dropped = [], []
    monkeypatch.setattr(cli, "Prowlarr", _FakeProwlarr)
    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(
        cli, "probe", lambda url, timeout=90.0, alive=None: Media(5978.0, MOANA2, "h264", 1080)
    )
    monkeypatch.setattr(playback, "start_play_unit", lambda key: None)
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
    """TorrServer со счётом раздач: кого подняли и кого убрали - по хэшам."""

    added: ClassVar[list[str]] = []
    dropped: ClassVar[list[str]] = []

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url, self.timeout = url, timeout

    def add(self, magnet: str) -> str:
        torrent_hash = f"hash-{magnet[:30]}"
        _FakeTorrServer.added.append(torrent_hash)
        return torrent_hash

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        return [TorrFile(0, "Moana.2.2024.1080p.mkv", 3 * GB)]

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> bool:
        _FakeTorrServer.dropped.append(torrent_hash)
        return True

    @classmethod
    def left(cls) -> set[str]:
        """Раздачи, которые после всего остались висеть в службе."""
        return set(cls.added) - set(cls.dropped)


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

    printed = capsys.readouterr().out
    assert "rus · Дубляж. (MovieDalen)" in printed
    assert "дорожек rus 8, беру дубляж (MovieDalen)" in printed, "выбор объяснён одной строкой"
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
    assert cli.main(["моана", "2"]) == 0

    printed = capsys.readouterr().out
    assert asked == [], "вопросов нет: и картина одна, и озвучка выбрана в прошлый раз"
    assert "rus · MVO (LostFilm)" in printed and "Озвучка:" not in printed
    assert State.load().entries[KEY].audio == 5


def test_new_with_a_voice_overwrites_the_memory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Явный флаг сильнее памяти и переписывает её."""
    _answers(monkeypatch)
    assert cli.main(["моана", "2", "--voice", "6"]) == 0
    assert cli.main(["моана", "2", "--new", "--voice", "3"]) == 0
    capsys.readouterr()

    saved = State.load().entries[KEY]
    assert (saved.audio, saved.voice) == (2, "rus · Дубляж. (Jaskier)")


def test_a_wrong_number_is_a_polite_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Дорожки с таким номером нет — честная строка и код «не нашли», а не показ."""
    monkeypatch.setattr(playback, "start_play_unit", lambda key: pytest.fail("вслепую не кастим"))
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
    monkeypatch.setattr(
        playback, "start_play_unit", lambda key: pytest.fail("voices ничего не играет")
    )

    assert cli.main(["voices", "моана 2"]) == 0

    printed = capsys.readouterr().out
    assert "  1. rus · Дубляж. (MovieDalen)   [дефолт]" in printed
    assert "  5. rus · MVO (TVShows)   [запомнено]" in printed
    assert "cast <запрос> --voice N" in printed
    assert "играю" not in printed


def test_the_voices_command_passes_a_noninteractive_picture_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cast voices`` понимает тот же ``--pick M``, что показ и таблица релизов."""
    seen: list[int | None] = []
    original = cli._pick_plan

    def pick(
        plans: list[cli._Plan],
        facts: object = None,
        pick: int | None = None,
        asked: str = "",
    ) -> cli._Plan:
        seen.append(pick)
        return original(plans, pick=1, asked=asked)

    monkeypatch.setattr(cli, "_pick_plan", pick)
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("меню не спрашиваем"))

    assert cli.main(["voices", "моана 2", "--pick", "2"]) == 0
    assert seen == [2]


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


def test_new_applies_the_named_voice_to_the_saved_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--new`` не имеет права молча выбросить соседний ``--voice``."""
    key = _serial()
    _answers(monkeypatch)

    assert cli.main(["киберпанк", "--new", "--voice", "5"]) == 0

    saved = State.load().entries[key]
    assert (saved.audio, saved.voice, saved.pos) == (4, "rus · MVO (TVShows)", 0.0)


def _serial(key: str = "tv:киберпанк:2022") -> str:
    """Сериал в состоянии: продолжение идёт по записи, поиска на этом пути нет."""
    state = State()
    state.put(
        key,
        Entry(
            title="Киберпанк",
            magnet="magnet:?xt=urn:btih:" + "b" * 40,
            kind="tv",
            query="киберпанк",
            season=1,
            episode=2,
            episodes=[[1, 1, 0], [1, 2, 1], [1, 3, 2]],
        ),
    )
    state.save()
    return key


def test_a_dry_run_with_a_voice_leaves_no_torrent_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 ``--voice`` поднимал раздачу ради дорожек и не убирал её НИКОГДА - даже всухую.

    Сухой прогон заведён затем, чтобы следов не оставалось, а след оставался самый
    дорогой: раздача живёт не в нашем процессе, а в TorrServer, до его перезапуска. И
    падает он тем вероятнее, чем их больше - замер: с одной раздачей тик проходит, со 120
    и живым чтением паника на первом же тике.
    """
    _serial()
    _answers(monkeypatch)
    monkeypatch.setattr(
        playback, "start_play_unit", lambda key: pytest.fail("сухой прогон не кастит")
    )

    assert cli.main(["киберпанк", "--voice", "5", "--dry"]) == 0

    assert _FakeTorrServer.added, "дорожки читаются из потока - раздачу поднять пришлось"
    assert _FakeTorrServer.left() == set(), "и всё поднятое убрано по своим хэшам"


def test_a_voice_torrent_is_handed_to_the_show_and_not_pulled_from_under_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Показ начался на том же магните - раздача теперь ЕГО, и убирать её нельзя.

    Уборка тут не «на всякий случай, вдруг лишняя»: у раздачи ровно один хозяин, и он
    меняется один раз - от вызова с ``--voice`` к юниту. Снести её на этом стыке значило
    бы выдернуть раздачу из-под показа, который сам её и играет.
    """
    key = _serial()
    _answers(monkeypatch)
    started: list[str] = []
    monkeypatch.setattr(playback, "start_play_unit", lambda name: started.append(name))

    assert cli.main(["киберпанк", "--voice", "5"]) == 0

    assert started == [key], "показ пошёл"
    assert _FakeTorrServer.dropped == [], "из-под начавшегося показа раздачу не выдёргиваем"


def test_a_voice_torrent_dies_with_the_show_that_never_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Юнит не поднялся - раздача, поднятая ради дорожек, остаётся без хозяина и уходит.

    Тот же исход у Ctrl-C на вопросе и у «серии в этой раздаче нет»: показа не будет, а
    раздача уже есть. До сих пор её не убирал никто.
    """
    _serial()
    _answers(monkeypatch)

    def refuse(key: str) -> None:
        raise InfraError("не запустился юнит torrcast-play")

    monkeypatch.setattr(playback, "start_play_unit", refuse)

    assert cli.main(["киберпанк", "--voice", "5"]) == 2

    assert _FakeTorrServer.added, "раздачу подняли"
    assert _FakeTorrServer.left() == set(), "и убрали, раз показа не вышло"


def test_the_old_flag_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--audio N`` — прежнее имя того же флага; ломать его незачем."""
    _answers(monkeypatch)

    assert cli.main(["моана", "2", "--audio", "6"]) == 0

    assert State.load().entries[KEY].voice == "rus · MVO (LostFilm)"


# --- 🔴 TC-178/TC-191: русская дорожка как условие «включилось», сквозь настоящий cli --


#: Дорожки тут про ЯЗЫК, а не про лестницу: одна дорожка на релиз, и весь вопрос в том,
#: русская она или нет. Лестницу озвучек проверяют живые наборы выше по файлу.
JAPANESE = (AudioTrack(0, "jpn", "Japanese", "aac", 2),)
RUSSIAN = (AudioTrack(0, "rus", "Дубляж", "ac3", 6),)


def _pool(
    monkeypatch: pytest.MonkeyPatch, *releases: tuple[str, str, tuple[AudioTrack, ...]]
) -> None:
    """Выдача из имён раздач и паспорт под каждую: имя, метка магнита, дорожки.

    Паспорт привязан к самой раздаче (метка магнита видна в адресе потока), а не к
    порядку вызовов: запасной релиз греется параллельно с верхом.
    """
    rows = [
        RawResult(name, tag * 40, 8 * GB, seeders)
        for seeders, (name, tag, _) in zip((90, 30), releases, strict=True)
    ]
    monkeypatch.setattr(_FakeProwlarr, "search", lambda self, query: list(rows))

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        for _, tag, tracks in releases:
            if f"btih:{tag * 10}" in url:
                return Media(5978.0, tracks, "h264", 1080, 1920)
        return Media(5978.0, JAPANESE, "h264", 1080, 1920)

    monkeypatch.setattr(cli, "probe", read)


def test_a_japanese_top_release_steps_aside_for_a_russian_one_below_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-178, случай первый: русская дорожка в выдаче ЕСТЬ - её и включаем.

    Имя врёт: обе раздачи обещают «[RUS(int)]», и порядок между ними решают сиды - у
    верха их втрое больше. Русского звука внутри у него при этом нет, и до правки играл бы
    он: обещание имени отбор проверял только на отборе, а лестница дорожек выбирала лучшее
    из того, что нашлось В ВЗЯТОМ релизе. Теперь паспорт решает годность, и показ уходит к
    соседу, сказав об этом одной строкой.
    """
    _pool(
        monkeypatch,
        ("Аниме / Anime (2020) WEB-DL 1080p [RUS(int)]", "c", JAPANESE),
        ("Аниме / Anime (2020) WEB-DL 1080p [RUS(int)]", "d", RUSSIAN),
    )
    prefixes: list[str] = []
    wait = cli._Bench._wait

    def watched_wait(
        self: cli._Bench,
        prep: cli._Prep,
        progress: Progress,
        prefix: str = "",
        limit: float = 0.0,
    ) -> None:
        prefixes.append(prefix)
        wait(self, prep, progress, prefix, limit)

    monkeypatch.setattr(cli._Bench, "_wait", watched_wait)
    _answers(monkeypatch)

    assert cli.main(["аниме"]) == 0

    printed = capsys.readouterr().out
    assert "релиз 1 без русской озвучки (японский) - беру 2" in printed
    assert prefixes[:2] == [
        "ищу русскую озвучку: релиз 1 из 2 - ",
        "ищу русскую озвучку: релиз 2 из 2 - ",
    ]
    assert "rus · Дубляж" in printed, "играет русская дорожка"
    assert "только японский звук" not in printed, "оправдываться не в чем"
    assert _FakeTorrServer.left() == {"hash-magnet:?xt=urn:btih:" + "d" * 10}, (
        "отложенный японский релиз не остаётся висеть в службе - её держит только показ"
    )


def test_a_dub_that_exists_only_next_to_the_video_is_named_out_loud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-191, случай второй: перевод в каталоге есть, но только ``RUS(ext)``.

    Русская дорожка лежит ОТДЕЛЬНЫМ ФАЙЛОМ, и подмешать её показ не умеет. Молча отдать
    японский под видом «включилось» нельзя, отправить выбирать раздачу руками - тоже
    неправда: выбирать не из чего. Строка говорит как есть.
    """
    _pool(
        monkeypatch,
        ("Аниме / Anime (2020) WEB-DL 1080p [RUS(ext), ENG, JAP+Sub]", "c", JAPANESE),
        ("Аниме / Anime (2020) WEB-DL 1080p [JAP+Sub]", "d", JAPANESE),
    )
    _answers(monkeypatch)

    assert cli.main(["аниме"]) == 0

    printed = capsys.readouterr().out
    assert "релиз 1 без русской озвучки (японский) - беру 2" in printed
    assert "русской озвучки нет ни в одной из проверенных раздач (2)" in printed
    assert "включаю релиз 1, звук японский" in printed
    assert "только японский звук - в каталоге перевод есть, но лежит отдельным файлом" in printed


def test_a_picture_nobody_ever_dubbed_still_plays_and_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-178, случай третий: русской дорожки нет ни у кого - это дыра каталога.

    Отказать значило бы отобрать у зрителя и то, что есть. Показ идёт, а строка называет
    и язык звука, и то, что перевода в каталоге нет вовсе.
    """
    _pool(
        monkeypatch,
        ("Аниме / Anime (2020) WEB-DL 1080p [JAP+Sub]", "c", JAPANESE),
        ("Аниме / Anime (2020) WEB-DL 1080p [JAP+Sub]", "d", JAPANESE),
    )
    _answers(monkeypatch)

    assert cli.main(["аниме"]) == 0

    printed = capsys.readouterr().out
    assert "русской озвучки нет ни в одной из проверенных раздач (2)" in printed
    assert "только японский звук, перевода в каталоге нет" in printed
