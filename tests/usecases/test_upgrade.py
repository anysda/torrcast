"""Сценарий ``cast --upgrade``: чем он отказывается обновляться и что считает удачей.

Закачки тут нет, и проверять её нечем: её ведёт загрузчик. Спрашивается ровно то, чего
загрузчик знать не вправе, - порядок отказов и чтение чужого кода возврата.
"""

from __future__ import annotations

import pytest

from tests.fakes.console import FakeConsole
from tests.fakes.playback_session import FakePlaybackSession
from tests.fakes.upgrade_environment import FakeUpgradeEnvironment
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_OK
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.usecases.upgrade import Upgrade


def _upgrade(
    session: FakePlaybackSession | None = None,
    environment: FakeUpgradeEnvironment | None = None,
    console: FakeConsole | None = None,
    language: str = "ru",
) -> Upgrade:
    return Upgrade(
        session or FakePlaybackSession(),
        console or FakeConsole(),
        environment or FakeUpgradeEnvironment(),
        "1.0.0",
        language,
    )


def test_the_latest_version_is_asked_for_by_handing_the_loader_the_installed_one() -> None:
    environment = FakeUpgradeEnvironment()

    assert _upgrade(environment=environment).run() == EXIT_OK
    assert environment.handed == [("/opt/torrcast/install", "1.0.0", "ru")]


def test_a_running_show_is_not_killed_silently() -> None:
    session = FakePlaybackSession(playing=True, play_key="movie:муха")
    session.shown = PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0)
    console, environment = FakeConsole(), FakeUpgradeEnvironment()

    assert _upgrade(session, environment, console).run() == EXIT_INFRA
    assert console.messages == [phrase("upgrade.show_is_on", what="«Муха»")]
    assert environment.handed == [], "показ идёт, а работа всё равно ушла загрузчику"


def test_a_show_whose_state_entry_is_lost_is_still_named_by_its_unit() -> None:
    """Запись состояния теряется, а юнит играет: имя обязано доехать из описания юнита.

    Поймано стендом: живой ``torrcast-play`` с описанием «Мумия (1999)» и пустым
    состоянием давал отказ «сейчас играет «»» - причина без причины.
    """
    session = FakePlaybackSession(playing=True, play_key="Мумия (1999)")
    session.shown = None
    console = FakeConsole()

    assert _upgrade(session, FakeUpgradeEnvironment(), console).run() == EXIT_INFRA
    assert console.messages == [phrase("upgrade.show_is_on", what="Мумия (1999)")]


def test_a_show_that_names_itself_nowhere_gets_a_refusal_without_empty_quotes() -> None:
    """Ни записи, ни описания - отказ всё равно обязан читаться как отказ, а не как «»."""
    session = FakePlaybackSession(playing=True, play_key="")
    console = FakeConsole()

    assert _upgrade(session, FakeUpgradeEnvironment(), console).run() == EXIT_INFRA
    assert console.messages == [phrase("upgrade.show_is_on_unnamed")]
    assert "«»" not in console.messages[0]


def test_the_show_is_asked_about_before_the_rights() -> None:
    """Отказ по правам чинится одной командой, а погашенная серия не возвращается."""
    session = FakePlaybackSession(playing=True)
    console = FakeConsole()

    _upgrade(session, FakeUpgradeEnvironment(root=False), console).run()

    assert console.messages != [phrase("upgrade.needs_root")]


def test_without_root_the_way_to_repeat_is_named() -> None:
    console = FakeConsole()

    assert _upgrade(environment=FakeUpgradeEnvironment(root=False), console=console).run() == (
        EXIT_INFRA
    )
    assert console.messages == [phrase("upgrade.needs_root")]


def test_a_copy_installed_before_the_loader_existed_hears_how_to_catch_up() -> None:
    console = FakeConsole()
    environment = FakeUpgradeEnvironment(installed_loader="")

    assert _upgrade(environment=environment, console=console).run() == EXIT_INFRA
    assert console.messages == [phrase("upgrade.no_loader")]
    assert environment.handed == []


def test_a_trimmed_indexer_catalogue_is_not_dressed_up_as_a_failure() -> None:
    """🔴 Код 2 установщик отдаёт штатно: каталог вышел беднее полного, но продукт стоит."""
    console = FakeConsole()

    assert _upgrade(environment=FakeUpgradeEnvironment(result=2), console=console).run() == EXIT_OK
    assert console.messages == []


def test_a_broken_install_names_the_version_that_stayed() -> None:
    console = FakeConsole()

    assert _upgrade(environment=FakeUpgradeEnvironment(result=1), console=console).run() == (
        EXIT_INFRA
    )
    assert console.messages == [phrase("upgrade.failed", version="1.0.0")]


def test_the_words_are_resolved_before_the_tree_is_rewritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 pip сносит пакет, из которого работает этот процесс, прямо в ходе передачи.

    Надпись, взятая ПОСЛЕ возврата, читалась бы уже из перезаписанного дерева. Проверка
    отнимает надписи ровно на время передачи работы: сценарий, разрешивший строку заранее,
    этого не заметит, а тот, кто спрашивает поздно, останется без слов.
    """
    console = FakeConsole()
    environment = FakeUpgradeEnvironment(result=1)
    said = phrase("upgrade.failed", version="1.0.0")

    def rewritten(*_args: object, **_keywords: object) -> str:
        raise AssertionError("надпись спрошена после того, как дерево уже переписано")

    def hand_off(loader: str, installed: str, language: str) -> int:
        monkeypatch.setattr("torrcast.usecases.upgrade.phrase", rewritten)
        return 1

    environment.hand_off = hand_off  # type: ignore[method-assign]

    assert _upgrade(environment=environment, console=console).run() == EXIT_INFRA
    assert console.messages == [said]


def test_without_root_but_with_sudo_the_command_repeats_itself_instead_of_refusing() -> None:
    """Отказ по правам - последнее средство, а не первое: пока есть чем поднять права,
    человеку незачем узнавать про них вовсе, он просто вводит пароль самому sudo."""
    console = FakeConsole()
    environment = FakeUpgradeEnvironment(root=False, sudo=True)

    assert _upgrade(environment=environment, console=console).run() == EXIT_OK
    assert console.messages == [phrase("upgrade.elevating")]
    assert environment.elevations == 1
    assert environment.handed == [], "работа ушла загрузчику от не-root"


def test_the_code_of_the_raised_run_comes_back_undressed() -> None:
    """Поднятая работа - та же работа: её код возврата и есть ответ команды. Отказ
    sudo (не тот пароль) обязан доехать отказом, а не «обновлено»."""
    environment = FakeUpgradeEnvironment(root=False, sudo=True, elevated_result=1)

    assert _upgrade(environment=environment).run() == 1


def test_a_running_show_is_asked_about_before_the_password() -> None:
    """Показ спрашивается раньше прав и в этом случае тоже: спросить пароль, чтобы
    следом отказать из-за идущей серии, - худший из возможных порядков."""
    session = FakePlaybackSession(playing=True)
    environment = FakeUpgradeEnvironment(root=False, sudo=True)

    assert _upgrade(session, environment).run() == EXIT_INFRA
    assert environment.elevations == 0
