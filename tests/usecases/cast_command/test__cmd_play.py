"""Зеркало счастливого пути: ранние выходы отвечают показом, а не проваливаются в поиск."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.world import GB, entry, release
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.choice import Choice
from torrcast.domain.episode import Episode
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.facts.origin import Origin
from torrcast.domain.media import Media
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch) -> None:
    """Паспорт приёмника на стенде спрашивать не у кого: профиль называется прямо.

    Настройки, уборка сирот и строка о занятом телевизоре тут настоящие: файл настроек
    свой у каждого теста, сирот в пустом состоянии нет, а занятого показа нет тем более.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))


def _remember(saved: object) -> None:
    state = WatchState()
    state.put("кино", saved)  # type: ignore[arg-type]
    watch_store().save(state)


def _never(*_args: object, **_rest: object) -> int:
    return pytest.fail("до поиска доходить нечему")


def test_a_saved_movie_is_continued_without_a_single_question() -> None:
    """Начатый фильм продолжается молча: до поиска этот путь не доходит вовсе."""
    _remember(entry(query="кино"))

    code = _cmd_play(Args(query=["кино"]), resume=lambda *args, **rest: EXIT_OK, choose=_never)

    assert code == EXIT_OK


def test_a_watched_movie_is_started_over_and_says_so() -> None:
    """Досмотренный фильм играется с начала - и это тоже ранний выход, а не поиск."""
    _remember(entry(query="кино", pos=7100.0))

    code = _cmd_play(Args(query=["кино"]), restart=lambda *args, **rest: EXIT_OK, choose=_never)

    assert code == EXIT_OK


def test_an_asked_menu_outranks_the_bookmark_and_says_nothing_about_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--menu`` - запрос «дай выбрать»: закладка на него не отвечает и не считает."""
    _remember(entry(query="кино", pos=7100.0))

    code = _cmd_play(
        Args(query=["кино"], menu=True),
        restart=_never,
        resume=_never,
        choose=lambda *args, **rest: EXIT_OK,
    )

    assert code == EXIT_OK
    assert "досмотрено" not in capsys.readouterr().out


def test_a_hand_named_menu_item_outranks_the_bookmark() -> None:
    """``--pick N`` называет картину номером - съесть этот номер закладке нечем."""
    _remember(entry(query="кино"))

    code = _cmd_play(
        Args(query=["кино"], pick=3),
        restart=_never,
        resume=_never,
        choose=lambda *args, **rest: EXIT_OK,
    )

    assert code == EXIT_OK


def test_the_code_of_the_bookmark_of_the_chosen_picture_reaches_the_caller() -> None:
    """Закладка выбранной картины отвечает показом - и её код уезжает наружу целым."""
    assert _cmd_play(Args(query=["кино"]), choose=lambda *args, **rest: EXIT_OK) == EXIT_OK


def test_a_hand_named_release_searches_the_bookmarked_episode_not_the_first() -> None:
    """``--release N`` у начатого сериала: в поиск уезжает серия закладки, а не s1e1."""
    _remember(
        entry(
            query="кино",
            kind="tv",
            season=5,
            episode=1,
            pos=265.0,
            episodes=[[5, 1, 0, 10**9], [5, 2, 1, 10**9]],
        )
    )
    seen: list[Args] = []

    def choose(_config: object, args: Args, *_rest: object, **_kw: object) -> int:
        seen.append(args)
        return EXIT_OK

    code = _cmd_play(Args(query=["кино"], release=2), restart=_never, resume=_never, choose=choose)

    assert code == EXIT_OK
    assert str(seen[0].episode) == "s5e1", "место в сериале - не выбор раздачи (TC-807)"


def test_the_played_file_names_the_episode_and_the_place_is_carried(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Пак пятого сезона под запросом «s1e1»: строка зовёт серию по ФАЙЛУ (TC-807)."""
    _remember(
        entry(
            query="кино",
            kind="tv",
            season=5,
            episode=1,
            pos=265.0,
            dur=1400.0,
            episodes=[[5, 1, 3, 10**9], [5, 2, 4, 10**9]],
        )
    )
    files = [
        TorrFile(index=3, name="кино/s05e01.mkv", size=8 * GB),
        TorrFile(index=4, name="кино/s05e02.mkv", size=8 * GB),
    ]
    pack = release("Кино / Movie WEB-DL 1080p")
    one = Plan(
        picture=Picture(title="Кино", year=1999, kind="tv", releases=[pack]),
        ranked=[pack],
        runtime=1400.0,
        warn_mbit=16.0,
        series=_Series(want=Episode(1, 1)),
    )
    prep = _Prep(number=1, release=pack)
    prep.video, prep.files = files[0], files
    prep.media = Media(
        duration=1400.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="h264",
        height=1080,
        video_bps=8.0 * 1e6,
    )

    class _Bench:
        def drop_all(self) -> None:
            pass

    class _Passport:
        def get(self) -> Origin:
            return Origin()

    def choose(*_args: object, **_kw: object) -> object:
        return [one], one, prep, _Bench(), _Passport()

    code = _cmd_play(
        Args(query=["кино"], release=1, dry=True),
        restart=_never,
        resume=_never,
        choose=choose,  # type: ignore[arg-type]
    )

    assert code == EXIT_OK
    out = capsys.readouterr().out
    assert "«Кино» s5e1" in out, "подпись серии - у файла, который играет, а не у запроса"
    assert "с 0:04:25" in out, "место закладки названо обычной строкой показа"
