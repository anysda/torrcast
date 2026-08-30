"""Какую дорожку играем и что после этого лежит в памяти картины."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests.fakes.composition import use_rank_console
from tests.fakes.console import FakeConsole
from tests.usecases.rank.releases import media, track
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.rank_settings import VOICE_MENU
from torrcast.domain.release import Release
from torrcast.usecases.rank.pick_voice import pick_voice


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет всего модуля - РУССКАЯ лестница озвучек, писанная до языкового яруса
    (:func:`torrcast.domain.voice_order._tier`). Умолчание продукта английское, и на нём
    набор остался бы зелёным, но мерил бы уже другой порядок: та же зелень отвечала бы
    на другой вопрос. Поэтому язык назван, а не унаследован."""


@dataclass
class _Args:
    """Ровно то, что правило у разобранной строки и спрашивает."""

    voice: int | str | None = None


DUB = track(0, "rus", "Дубляж")
ORIG = track(1, "eng", "Original")


@pytest.fixture
def console(monkeypatch: pytest.MonkeyPatch) -> FakeConsole:
    fake = FakeConsole()
    use_rank_console(monkeypatch, fake)
    return fake


def test_the_happy_path_asks_nothing_and_remembers_nothing(console: FakeConsole) -> None:
    """Дорожка выбирается сама, а её подпись печатается в строке запуска."""
    assert pick_voice(media(tracks=(DUB, ORIG)), _Args()) == (0, "")
    assert console.questions == []


def test_a_hand_named_number_is_taken_and_remembered(console: FakeConsole) -> None:
    """Явный выбор - и только он - пишется в память картины."""
    assert pick_voice(media(tracks=(DUB, ORIG)), _Args(voice=2)) == (1, ORIG.label)


def test_a_studio_named_by_the_track_is_taken_and_remembered(console: FakeConsole) -> None:
    tracks = (DUB, track(1, "rus", "MVO (NewStation)"))

    assert pick_voice(media(tracks=tracks), _Args(voice="new station")) == (1, "NewStation")


def test_a_part_of_the_track_label_is_an_honest_refusal(console: FakeConsole) -> None:
    tracks = (track(0, "rus", "MVO (LostFilm)"), ORIG)

    with pytest.raises(NotFoundError, match="озвучки «MVO» в этом релизе нет"):
        pick_voice(media(tracks=tracks), _Args(voice="MVO"))


def test_a_studio_named_only_by_the_release_is_taken_and_remembered(console: FakeConsole) -> None:
    pack = Release(raw_name="Сериал S05 WEB-DL, 2 x MVO (TVShows, NewStation)", title="Сериал")
    tracks = (track(0, "rus", None), track(1, "rus", None))

    assert pick_voice(media(tracks=tracks), _Args(voice="NEWSTATION"), studios=pack.studios) == (
        1,
        "NewStation",
    )


def test_a_remembered_studio_survives_a_release_with_plain_labels(console: FakeConsole) -> None:
    pack = Release(raw_name="Сериал S05 WEB-DL, 2 x MVO (TVShows, NewStation)", title="Сериал")
    tracks = (track(0, "rus", None), track(1, "rus", None))

    assert pick_voice(media(tracks=tracks), _Args(), "NewStation", studios=pack.studios) == (
        1,
        "NewStation",
    )


def test_a_studio_word_that_is_absent_is_an_honest_refusal(console: FakeConsole) -> None:
    with pytest.raises(NotFoundError, match="озвучки «NewStation» в этом релизе нет"):
        pick_voice(media(tracks=(DUB, ORIG)), _Args(voice="NewStation"))


def test_the_menu_shows_up_only_on_voice_without_a_number(console: FakeConsole) -> None:
    console.answers.append("2")

    index, remembered = pick_voice(media(tracks=(DUB, ORIG)), _Args(voice=VOICE_MENU))

    assert (index, remembered) == (1, ORIG.label)
    assert any("Озвучка:" in message for message in console.messages)


def test_a_lone_track_is_not_a_question(console: FakeConsole) -> None:
    assert pick_voice(media(tracks=(DUB,)), _Args(voice=VOICE_MENU)) == (0, DUB.label)
    assert console.questions == []


def test_a_remembered_voice_absent_here_is_said_out_loud_and_kept(console: FakeConsole) -> None:
    """Память живёт на картину, а релиз временный: выбор человека не забывается."""
    index, remembered = pick_voice(media(tracks=(ORIG,)), _Args(), remembered="Дубляж")

    assert (index, remembered) == (ORIG.index, "Дубляж")
    assert console.messages == ["озвучки «Дубляж» в этом релизе нет - беру обычную"]


def test_a_file_without_a_single_track_is_an_honest_error(console: FakeConsole) -> None:
    with pytest.raises(InfraError):
        pick_voice(media(), _Args())


def test_a_number_that_does_not_exist_is_an_honest_refusal(console: FakeConsole) -> None:
    with pytest.raises(NotFoundError):
        pick_voice(media(tracks=(DUB,)), _Args(voice=9))


def test_a_native_picture_plays_its_own_track_without_a_question() -> None:
    """Счастливый путь у русского фильма: играет он сам, а не переозвучка поверх него."""
    tracks = (track(0, "rus", "[DUB] DVD-R5 AMALGAMA"), track(1, "rus", None))

    assert pick_voice(media(tracks=tracks), _Args(), "", True) == (1, "")
    assert pick_voice(media(tracks=tracks), _Args()) == (0, "")


def test_a_hand_picked_voice_of_a_native_picture_is_still_the_hand_picked_one() -> None:
    """Явный выбор сильнее любой лестницы: ``--voice 1`` берёт первую дорожку."""
    tracks = (track(0, "rus", "[DUB] DVD-R5 AMALGAMA"), track(1, "rus", None))

    assert pick_voice(media(tracks=tracks), _Args(voice=1), "", True)[0] == 0
