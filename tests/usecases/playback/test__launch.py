"""Зеркало запуска показа: отказ безнадёжному, юнит и ожидание КАРТИНКИ, а не упаковки."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from tests.fakes import composition
from tests.fakes.clock import FakeClock
from tests.fakes.show_unit import FakeShowUnit
from tests.usecases.playback.world import FakeProgress, FakeShow, touch_segment
from torrcast.adapters.stream_pack.mark_landed import mark_landed
from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.hls_settings import PLAYING_FLAG
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.abandon import slot as abandon_slot
from torrcast.ports.show_unit.show_unit import ShowUnit
from torrcast.ports.state_store.slot import store
from torrcast.usecases.playback import _show_state
from torrcast.usecases.playback._launch import _await_playing, _launch
from torrcast.usecases.playback.hls_root import hls_root
from torrcast.usecases.playback.launch_owner import LaunchOwner
from torrcast.usecases.screen_line import screen_line
from torrcast.usecases.start_clock import _Clock


def _timeout_prefix(secs: float) -> str:
    """Постоянная часть надписи о несостоявшемся старте - до ответа юнита."""
    marker = "\x00"
    return phrase("playback.did_not_start_timeout", secs=f"{secs:.0f}", said=marker).split(marker)[
        0
    ]


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

    want = phrase("playback.did_not_start", why="юнит выпал")
    with pytest.raises(InfraError, match=re.escape(want)):
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

    with pytest.raises(InfraError, match=re.escape(_timeout_prefix(3.0))):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
        )

    assert unit.stopped == 1, "юнит, не давший картинки, обязан быть погашен"


def test_the_budget_does_not_kill_a_show_the_viewer_is_watching(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Бюджет вышел, а показ ИДЁТ - гасить его нельзя: зритель смотрит серию.

    🔴 TC-884, 29-08-2026. Флажок картинки лежит в каталоге, куда ходит не только показ, и
    его сняли посреди сеанса. CLI досидел бюджет, не спросил юнит вовсе и погасил показ,
    шедший пятую минуту: экран потух посреди серии, а в след ушло «показ не начался за
    350 с» рядом со словом ``PLAYING`` из того же журнала. Отсутствие флажка ничего не
    доказывает - доказывает движение указателя, и спросить о нём надо ДО казни.

    Молчание тут было бы бедой не косметической: живой показ идёт дальше без единого
    слова человеку, и «что вообще произошло» узнать неоткуда, кроме следа.
    """
    out = tmp_path / "hls"
    out.mkdir()
    landed = 26 * 60 + 58.0  # куда завели показ: «Домохозяйки» s1e8, 0:26:58
    said_line = screen_line("[сеанс 7]", landed + 324.0, 2640.0, "PLAYING")
    unit = FakeShow(said=["[сеанс 7] упаковка пошла", said_line])

    _await_playing(
        Config(hls_dir=str(out)),
        FakeProgress(),
        3.0,
        clock=FakeClock(now=100.0),
        unit=cast(ShowUnit, unit),
        start=landed,
    )

    assert unit.stopped == 0, "показ, двигающий указатель, гасить нечем и не за что"
    want = phrase("playback.picture_undetected_but_playing", secs="3", said=said_line)
    assert want in capsys.readouterr().out, "зритель обязан узнать, почему казни не было"


def test_the_backward_landing_of_tc_1002_does_not_trip_the_bookmark_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """TC-1010. Показ сел НИЖЕ закладки - запасной путь обязан сверяться с местом посадки.

    После TC-1002 :func:`torrcast.usecases.feed_pack.feed_restart._begin` вправе взять
    опорный кадр НИЖЕ закладки, а отвод назад на неудачном заходе отступает ещё дальше.
    Указатель приёмника тогда честно меньше закладки, но больше настоящего места посадки -
    и сверка с самой закладкой погасила бы показ, который зритель уже смотрит.

    Молчание тут было бы бедой не косметической: показ прошёл на грани казни без единого
    слова человеку о том, что вообще случилось и по какому следу его отпустили.
    """
    out = tmp_path / "hls"
    out.mkdir()
    bookmark = 2500.0
    landed = 2450.0
    mark_landed(out, landed)  # то же число, что кладёт `_play` после `feed.begin`
    said_line = screen_line("[сеанс 7]", 2470.0, 3000.0, "PLAYING")
    unit = FakeShow(said=["[сеанс 7] упаковка пошла", said_line])

    killed_by_timeout = False
    try:
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
            start=bookmark,
        )
    except InfraError:
        killed_by_timeout = True

    assert not killed_by_timeout and unit.stopped == 0, (
        "показ, продвинувшийся от настоящей посадки, гасить не за что"
    )
    want = phrase("playback.picture_undetected_but_playing", secs="3", said=said_line)
    assert want in capsys.readouterr().out, "зритель обязан узнать, почему казни не было"


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

    with pytest.raises(InfraError, match=re.escape(_timeout_prefix(3.0))):
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

    with pytest.raises(InfraError, match=re.escape(_timeout_prefix(3.0))):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
            start=landed,
        )

    assert unit.stopped == 1, "строка не сдвинулась за весь бюджет - показа за ней нет"


def test_a_relaunch_does_not_carry_a_past_sessions_frame_into_the_new_one(
    monkeypatch: pytest.MonkeyPatch, show_unit: FakeShowUnit
) -> None:
    """Кадр ПРОШЛОГО сеанса не доказывает кадра ЭТОГО: запись обязана начать его заново.

    🔴 TC-1002. Без сброса запись, уже видевшая кадр в прошлом сеансе (``moved=True``),
    несла бы это враньё в новый запуск: приёмник в новом сеансе может не дать ни кадра
    вовсе, а мост Home Assistant прочёл бы уцелевший флаг как «идёт» и мог бы назвать
    чёрный экран паузой - ту же ошибку, что и с сырой позицией на диске.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))
    monkeypatch.setattr(_show_state, "forget_playing", lambda out: None)
    monkeypatch.setattr(_show_state, "start_play_unit", lambda key, here=False: None)
    composition.use_await_playing(monkeypatch, lambda *args, **kwargs: None)

    key = "movie:кино"
    entry = Entry(title="Кино", magnet="magnet:?xt=1", pos=2335.8, moved=True)

    _launch(Config(), key, entry, "«Кино»", _Clock())

    saved = store().load().get(key)
    assert saved is not None
    assert saved.moved is False, "новый запуск начинает факт кадра с чистого листа"


def test_a_raise_the_person_called_off_never_reaches_the_unit(
    monkeypatch: pytest.MonkeyPatch, show_unit: FakeShowUnit
) -> None:
    """🔴 TC-1022. Показ, от которого отказались, не поднимается после отказа.

    Подъём идёт минутами, и отказ человека приходит посреди него. Спрошено ДО юнита
    нарочно: поднять показ и тут же погасить - это чужой кадр на экране и лишний сендер
    на приёмнике, а не аккуратная отмена.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))
    monkeypatch.setattr(_show_state, "forget_playing", lambda out: None)
    raised: list[str] = []
    monkeypatch.setattr(_show_state, "start_play_unit", lambda key, here=False: raised.append(key))
    composition.use_await_playing(monkeypatch, lambda *args, **kwargs: None)
    abandon_slot.install(lambda: True)

    with pytest.raises(CancelledError, match=re.escape(phrase("playback.abandoned"))):
        _launch(
            Config(),
            "movie:кино",
            Entry(title="Кино", magnet="magnet:?xt=1"),
            "«Кино»",
            _Clock(),
        )

    assert raised == [], f"показ, от которого отказались, всё равно подняли: {raised}"


def test_a_show_called_off_while_it_waited_for_the_picture_is_put_out_at_once(
    tmp_path: Path,
) -> None:
    """Отказ, пришедший при уже живом юните, гасит показ здесь, а не через бюджет.

    Юнит поднимается через десяток секунд после начала подъёма, и отказ человека может
    прийти в ту самую долю секунды, когда юнита ещё не было: тогда снять его снаружи
    некому. Ожидание картинки спрашивает отказ на каждом своём круге и гасит показ само.
    """
    out = tmp_path / "hls"
    out.mkdir()
    unit = FakeShow()
    abandon_slot.install(lambda: True)

    with pytest.raises(CancelledError, match=re.escape(phrase("playback.abandoned"))):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
        )

    assert unit.stopped == 1, "показ, от которого отказались, остался жить"


def test_a_wait_whose_launch_was_taken_over_leaves_the_new_show_alone(tmp_path: Path) -> None:
    """🔴 TC-1203. Юнит под нашим именем уже чужой: его флажок - не наша картинка.

    Прежде бот, чей подъём снял показ из веба, дожидался чужого кадра и звал его своим -
    или чужого отказа и звал своим отказом. Чужой показ при этом не гасится: он не наш.
    """
    out = tmp_path / "hls"
    out.mkdir()
    mine = LaunchOwner.claim(out)
    LaunchOwner.claim(out)  # чужой запуск поставил свою метку поверх
    (out / PLAYING_FLAG).write_text("")  # и его показ уже дал кадр
    unit = FakeShow()

    with pytest.raises(CancelledError, match=re.escape(phrase("playback.abandoned"))):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
            owner=mine,
        )

    assert unit.stopped == 0, "чужой показ погашен ожиданием, которое его не поднимало"


def test_a_unit_put_out_by_another_launch_is_not_called_our_refusal(tmp_path: Path) -> None:
    """Чужой запуск погасил наш юнит - это отмена, а не «показ не запустился: <его строка>»."""
    out = tmp_path / "hls"
    touch_segment(out)
    mine = LaunchOwner.claim(out)
    LaunchOwner.claim(out)
    unit = FakeShow(alive=False, reason="прогрето 0:04:51 из 2:16:42 - грею дальше")

    with pytest.raises(CancelledError, match=re.escape(phrase("playback.abandoned"))):
        _await_playing(
            Config(hls_dir=str(out)),
            FakeProgress(),
            3.0,
            clock=FakeClock(now=100.0),
            unit=cast(ShowUnit, unit),
            owner=mine,
        )


def test_a_show_that_did_not_come_up_gives_the_saved_place_back(
    monkeypatch: pytest.MonkeyPatch, show_unit: FakeShowUnit
) -> None:
    """🔴 TC-1203. Отказ показа не стоит зрителю места (прод 11-09-2026, s3e14 → s1e1).

    Стартовая запись показа ложится под ключ картины до юнита. Показ не поднялся - и под
    ключом обязана остаться прежняя запись, а не стартовая: иначе и бот дальше играет
    s1e1 с нуля.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))
    monkeypatch.setattr(_show_state, "forget_playing", lambda out: None)
    monkeypatch.setattr(_show_state, "start_play_unit", lambda key, here=False: None)

    def refused(*args: object, **kwargs: object) -> None:
        raise InfraError(phrase("playback.did_not_start", why="юнит выпал"))

    composition.use_await_playing(monkeypatch, refused)
    key = "tv:сериал"
    place = Entry(title="Сериал", magnet="magnet:?xt=1", kind="tv", season=3, episode=14, pos=546.0)
    state = store().load()
    state.put(key, place)
    store().save(state)

    with pytest.raises(InfraError):
        _launch(Config(), key, replace(place, episode=1, season=1, pos=0.0), "«Сериал»", _Clock())

    saved = store().load().get(key)
    assert saved is not None
    assert (saved.season, saved.episode, saved.pos) == (3, 14, 546.0)


def test_a_launch_hands_its_own_claim_to_the_wait(
    monkeypatch: pytest.MonkeyPatch, show_unit: FakeShowUnit
) -> None:
    """Ожидание картинки знает, чей это подъём, и узнаёт, что его снял следующий запуск.

    Сверка метки в самом ожидании ничего не стоит, если запуск её туда не передал: бот,
    чей подъём снял показ из веба, снова ждал бы чужого кадра и звал бы его своим.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))
    monkeypatch.setattr(_show_state, "forget_playing", lambda out: None)
    monkeypatch.setattr(_show_state, "start_play_unit", lambda key, here=False: None)
    handed: list[LaunchOwner | None] = []

    def waited(*args: object, owner: LaunchOwner | None = None, **kwargs: object) -> None:
        handed.append(owner)

    composition.use_await_playing(monkeypatch, waited)
    config = Config()

    _launch(config, "movie:кино", Entry(title="Кино", magnet="magnet:?xt=1"), "«Кино»", _Clock())
    mine = handed[0] if handed else None
    assert mine is not None, "ожидание не знает, чей подъём оно ждёт"
    assert mine.taken_over() is False, "свой же подъём звать снятым нельзя"

    LaunchOwner.claim(hls_root(config.hls_dir))  # следующий запуск, веб или бот

    assert mine.taken_over() is True, "снятый подъём не узнал, что показ уже чужой"
