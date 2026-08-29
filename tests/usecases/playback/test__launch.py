"""Зеркало запуска показа: отказ безнадёжному, юнит и ожидание КАРТИНКИ, а не упаковки."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.fakes import composition
from tests.fakes.clock import FakeClock
from tests.usecases.playback.world import FakeProgress, FakeShow, touch_segment
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.hls_settings import PLAYING_FLAG
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.show_unit.show_unit import ShowUnit
from torrcast.usecases.playback._launch import _await_playing, _refuse_hopeless
from torrcast.usecases.screen_line import screen_line


def test_a_frame_the_receiver_never_takes_is_refused_before_the_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4К без перекода приёмник не берёт вовсе - отказ печатается до всякого ffmpeg."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))
    config = Config(recode=False)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", frame=2160, quality="2160p")

    with pytest.raises(NotFoundError, match="такой кадр приёмник берёт только ужатым"):
        _refuse_hopeless(config, entry)


def test_the_same_record_plays_when_the_whole_recode_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ужать кадр умеет сплошной перекод - значит отказывать тут нечему."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))

    _refuse_hopeless(Config(recode=True), Entry(title="Кино", magnet="magnet:?xt=1", frame=2160))


def test_a_record_of_an_older_version_plays_as_it_did(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кадр ноль - запись прежней версии: молчим там, где не знаем."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))

    _refuse_hopeless(Config(recode=False), Entry(title="Кино", magnet="magnet:?xt=1"))


def test_the_flag_of_the_picture_ends_the_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ждут КАРТИНКУ: флажок кладёт юнит, и ровно по нему ожидание кончается."""
    out = tmp_path / "hls"
    out.mkdir()
    (out / PLAYING_FLAG).write_text("")
    progress = FakeProgress()

    _await_playing(
        Config(hls_dir=str(out)),
        progress,
        5.0,
        clock=FakeClock(now=100.0),
        unit=cast(ShowUnit, FakeShow()),
    )

    assert progress.phases[-1] == ""


def test_a_dead_unit_ends_the_waiting_with_its_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Юнит выпал - ждать нечего, и причина берётся у него же, а не выдумывается."""
    out = tmp_path / "hls"
    touch_segment(out)

    with pytest.raises(InfraError, match="показ не запустился: юнит выпал"):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            5.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, FakeShow(alive=False, reason="юнит выпал")),
        )


def test_the_budget_of_the_start_is_not_endless(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Бюджет старта вышел - юнит гасится, а человеку называется срок, а не молчание."""
    out = tmp_path / "hls"
    out.mkdir()
    unit = FakeShow()

    with pytest.raises(InfraError, match="показ не начался за 3 с"):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
        )

    assert unit.stopped == 1, "юнит, не давший картинки, обязан быть погашен"


def test_the_budget_does_not_kill_a_show_the_viewer_is_watching(tmp_path: Path) -> None:
    """Бюджет вышел, а показ ИДЁТ - гасить его нельзя: зритель смотрит серию.

    🔴 TC-884, 29-08-2026. Флажок картинки лежит в каталоге, куда ходит не только показ, и
    его сняли посреди сеанса. CLI досидел бюджет, не спросил юнит вовсе и погасил показ,
    шедший пятую минуту: экран потух посреди серии, а в след ушло «показ не начался за
    350 с» рядом со словом ``PLAYING`` из того же журнала. Отсутствие флажка ничего не
    доказывает - доказывает движение указателя, и спросить о нём надо ДО казни.
    """
    out = tmp_path / "hls"
    out.mkdir()
    landed = 26 * 60 + 58.0  # куда завели показ: «Домохозяйки» s1e8, 0:26:58
    unit = FakeShow(
        said=[
            "[сеанс 7] упаковка пошла",
            screen_line("[сеанс 7]", landed + 324.0, 2640.0, "PLAYING"),
        ]
    )

    _await_playing(
        Config(hls_dir=str(out)),
        FakeProgress(),
        3.0,
        clock=FakeClock(now=100.0),
        unit=cast(ShowUnit, unit),
        start=landed,
    )

    assert unit.stopped == 0, "показ, двигающий указатель, гасить нечем и не за что"


def test_a_receiver_stuck_at_the_landing_point_is_still_a_failed_start(tmp_path: Path) -> None:
    """Слово ``PLAYING`` без сдвига указателя картинкой не является - юнит гасится.

    Приёмник объявляет себя играющим раньше первого кадра и держит указатель на месте
    захода. Прими ограждение живого показа это слово за картинку - оно перестало бы
    отличать идущий показ от не начавшегося вовсе, и неудачный старт висел бы на экране
    чёрным до утра.
    """
    out = tmp_path / "hls"
    out.mkdir()
    landed = 26 * 60 + 58.0
    unit = FakeShow(
        said=["[сеанс 7] упаковка пошла", screen_line("[сеанс 7]", landed, 2640.0, "PLAYING")]
    )

    with pytest.raises(InfraError, match="показ не начался за 3 с"):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
            start=landed,
        )

    assert unit.stopped == 1, "старта не было - юнит обязан быть погашен, как и прежде"


def test_a_line_left_by_a_previous_show_does_not_save_a_dead_one(tmp_path: Path) -> None:
    """🔴 Строка из журнала прошлого сеанса живым показом не является - юнит гасится.

    Имя юнита переживает показы: журнал за ним общий, а послесловие systemd из ответа
    отсеивается. Свежий юнит, вставший колом до первой своей строки, отвечает хвостом
    ПРЕДЫДУЩЕЙ серии - словом ``PLAYING`` и указателем далеко за местом захода. Прими
    ограждение живого показа этот хвост за картинку - оно отвечало бы «показ идёт» там,
    где меряет мертвеца, и чёрный экран висел бы до утра при бодром выводе CLI.
    """
    out = tmp_path / "hls"
    out.mkdir()
    landed = 26 * 60 + 58.0
    unit = FakeShow(reason=screen_line("[сеанс 6]", landed + 900.0, 2640.0, "PLAYING"))

    with pytest.raises(InfraError, match="показ не начался за 3 с"):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
            start=landed,
        )

    assert unit.stopped == 1, "строка не сдвинулась за весь бюджет - показа за ней нет"
