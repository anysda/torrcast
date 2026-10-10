"""Показ из вкладки: её ключ решает профиль головы и уезжает в юнит тем же доводом."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.test__cmd_play import _never, _one_film, _OnePassport
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import BROWSER, CAUTIOUS, Profile
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.playback.hls_root import HLS_ENV


def _played(
    monkeypatch: pytest.MonkeyPatch, tab: str, tv: str | None = None
) -> tuple[Profile, object]:
    """Профиль, которым грелась голова, и ключ, отданный юниту; ``tv`` - телевизор машины."""
    Path(os.environ["TORRCAST_CONFIG"]).write_text(json.dumps({"receiver": "browser", "tv": tv}))
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "паспорта нет"))
    one, prep = _one_film()
    warmed: list[Profile] = []
    handed: list[object] = []

    def launch(*_args: object, **kw: object) -> int:
        handed.append(kw.get("tab"))
        return EXIT_OK

    monkeypatch.setattr("torrcast.usecases.cast_command._cmd_play._launch", launch)

    class _Bench:
        def drop_all(self) -> None:
            return None

    class _Head:
        def want(self, _config: object, profile: Profile, *_rest: object) -> None:
            warmed.append(profile)

    def choose(*_args: object, **_kw: object) -> object:
        return [one], one, prep, _Bench(), _OnePassport()

    code = _cmd_play(
        Args(query=["кино"], here=True, tab=tab),
        restart=_never,
        resume=_never,
        choose=choose,  # type: ignore[arg-type]
        head=_Head(),  # type: ignore[arg-type]
    )
    assert code == EXIT_OK
    return warmed[0], handed[0]


def test_a_measured_tab_warms_and_plays_with_its_own_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _played(monkeypatch, "chromium-linux") == (BROWSER, "chromium-linux")


@pytest.mark.parametrize("tab", ["", "webkit-ios"])
def test_a_silent_or_unmeasured_tab_warms_as_dev_did(
    monkeypatch: pytest.MonkeyPatch, tab: str
) -> None:
    """Отрицательная проба: без ключа или с незамеренным голова греется порогами ``dev``."""
    assert _played(monkeypatch, tab) == (CAUTIOUS, tab)


@pytest.mark.parametrize(("key", "tv"), [("k1", False), ("", True)])
def test_the_busy_line_names_whoever_holds_the_show(
    monkeypatch: pytest.MonkeyPatch, key: str, tv: bool
) -> None:
    """Строка «сейчас идёт» судит по ящику: показ вкладки - браузер, иначе прежний телевизор."""
    write_web_box(Path(os.environ[HLS_ENV]), url="http://x/out.m3u8", title="Кино", at=0.0, key=key)
    said: list[object] = []
    monkeypatch.setattr(
        "torrcast.usecases.cast_command._cmd_play._say_showing",
        lambda *_a, **kw: said.append(kw.get("tv")),
    )

    _played(monkeypatch, "chromium-linux")

    assert said == [tv]


@pytest.mark.parametrize(("tv", "said"), [("Living Room", [True]), (None, [False])])
def test_a_tab_show_carried_to_the_tv_is_named_the_tv(
    monkeypatch: pytest.MonkeyPatch, tv: str | None, said: list[bool]
) -> None:
    """Ящик вкладки без ``tv``: при названном телевизоре это может быть показ «На ТВ».

    Перенос «На ТВ» ящик не переписывает, и машина с телевизором слышит прежнее «на
    телевизоре»; браузер назван только у машины без телевизора (``tv: null``).
    """
    box = Path(os.environ[HLS_ENV])
    write_web_box(box, url="http://x/out.m3u8", title="Кино", at=0.0, key="k1")
    heard: list[object] = []
    monkeypatch.setattr(
        "torrcast.usecases.cast_command._cmd_play._say_showing",
        lambda *_a, **kw: heard.append(kw.get("tv")),
    )

    _played(monkeypatch, "chromium-linux", tv)

    assert heard == said
