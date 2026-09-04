"""Разговор с приёмником: LOAD, чистое приложение, чужая сессия и ожидание картинки."""

from __future__ import annotations

from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Device, Status, Wired
from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.cast.hls_hints import HLS_HINTS, HLS_TYPE
from torrcast.domain.segment_container import FMP4


class _Loading:
    """Медиаконтроллер, запоминающий, с чем именно к нему пришёл LOAD."""

    def __init__(self, status: Status) -> None:
        self.status = status
        self.loads: list[dict[str, Any]] = []
        self.said: list[str] = []
        self.active = 0

    def play_media(self, url: str, kind: str, **rest: Any) -> None:
        self.loads.append({"url": url, "kind": kind, **rest})

    def pause(self) -> None:
        """Команда паузы: приёмник её берёт и встаёт на месте."""
        self.said.append("pause")
        self.status.player_state = "PAUSED"
        self.status.player_is_playing = False

    def block_until_active(self, timeout: float = 0.0) -> None:
        self.active += 1

    def update_status(self) -> None:
        return None


def _receiver(status: Status | None = None, **rest: Any) -> Wired:
    device = Device()
    device.media_controller = _Loading(status if status is not None else Status())  # type: ignore[assignment]
    made = Wired(device=device, **rest)
    made._url, made._title = "http://дом/поток.m3u8", "Моана"
    return made


def test_the_load_carries_the_hls_hints_and_a_vod_stream_type() -> None:
    """BUFFERED, а не LIVE: манифест VOD знает длительность, и шкала пультом работает.

    Подсказки формата обязательны: без них Default Media Receiver отвечает LOAD ERROR
    на муксованный TS.
    """
    receiver = _receiver()

    receiver._load(1272.4)

    controller = receiver.device.media_controller
    assert isinstance(controller, _Loading)
    (load,) = controller.loads
    assert load["url"] == "http://дом/поток.m3u8"
    assert load["kind"] == HLS_TYPE
    assert load["media_info"] == HLS_HINTS
    assert load["stream_type"] == "BUFFERED"
    assert load["current_time"] == 1272.4
    assert controller.active == 1, "LOAD ждёт, пока сессия станет активной"


def test_fmp4_load_carries_the_lowercase_segment_hint() -> None:
    receiver = _receiver()
    receiver.segment_container = FMP4

    receiver._load()

    controller = receiver.device.media_controller
    assert isinstance(controller, _Loading)
    assert controller.loads[0]["media_info"] == {
        "hlsSegmentFormat": "fmp4",
        "hlsVideoSegmentFormat": "fmp4",
        "hlsAudioSegmentFormat": "fmp4",
    }


def test_a_new_load_starts_with_a_clean_reason_of_refusal() -> None:
    """Причина не имеет права переезжать с одной загрузки на следующую."""
    receiver = _receiver()
    receiver._error_code = 905

    receiver._load()

    assert receiver._error_code is None


def test_the_session_is_remembered_so_a_foreign_show_is_not_taken_down() -> None:
    """По сессии :meth:`_ours` и отличит наш показ от чужого, когда придёт пора закрывать."""
    receiver = _receiver()

    receiver._load()

    assert receiver._session == "наша"


def test_a_stuck_app_is_closed_together_with_our_own_connection(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Одного ``quit_app`` мало, замерено трижды: LOAD по ТОМУ ЖЕ сокету поднимает его назад.

    Показ тогда не начинается, приёмник стоит в IDLE до самой смерти юнита, а новый
    процесс с новым соединением поднимает картинку за 3 с.
    """
    clock = FakeClock()
    receiver = _receiver(clock=clock)

    receiver._restart_app()

    assert receiver.device.said == ["quit_app", "disconnect"]
    assert receiver._cast is None, "следующий подъём соединения будет новым"
    assert clock.sleeps == [receiver.LOAD_PAUSE]
    assert "receiver got stuck" in capsys.readouterr().out


def test_a_foreign_app_on_the_screen_is_not_ours() -> None:
    """Приложение не наше - трогать нечего."""
    device = Device(app="чужое")
    receiver = Wired(device=device)

    assert receiver._ours() is False


def test_a_foreign_session_in_our_app_is_not_ours_either() -> None:
    """Приложение то же, а сессию поднял кто-то другой: это чужой показ."""
    receiver = Wired(device=Device(session="чужая"))
    receiver._session = "наша"

    assert receiver._ours() is False


def test_a_foreign_content_in_our_own_session_is_not_ours() -> None:
    """В наше приложение загрузился другой сендер - ``session_id`` при этом не меняется."""
    receiver = Wired()
    receiver._session, receiver._url = "наша", "http://дом/наш.m3u8"
    receiver.device.media_controller.status.content_id = "http://чужой/поток.m3u8"

    assert receiver._ours() is False


def test_an_empty_screen_is_free_for_a_resurrection() -> None:
    """Пустой экран и заставка - ровно так выглядит ТВ, бросивший наш показ."""
    assert Wired(device=Device(app=""))._free() is True
    assert Wired(device=Device(app="E8C28D3C"))._free() is True
    assert Wired(device=Device(app="чужое"))._free() is False


def test_a_playing_receiver_settles_at_once() -> None:
    """Приёмник заиграл - ждать больше нечего."""
    clock = FakeClock()
    receiver = _receiver(Status(state="PLAYING"), clock=clock)

    assert receiver._settle(60.0) is True


def test_a_silent_receiver_is_reloaded_and_then_given_up_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Потолок повторов ставит профиль, а не бюджет ожидания.

    Иначе счёт вёлся бы временем, и на неигравшем релизе в приёмник уходил бы десяток
    LOAD подряд, всё глубже загоняя его, пока прогон висит перед пустым экраном.
    """
    clock = FakeClock()
    receiver = _receiver(Status(state="IDLE", idle_reason="ERROR"), clock=clock)

    assert receiver._settle(600.0) is False
    assert receiver._reloads == receiver.profile.load_retries
    controller = receiver.device.media_controller
    assert isinstance(controller, _Loading)
    assert len(controller.loads) == receiver.profile.load_retries
    assert "LOAD was not taken" in capsys.readouterr().out


class _Watched(Wired):
    """Приёмник, помнящий, сколько повторов лента УЖЕ знала, пока шёл очередной.

    Ради ПОРЯДКА: запись, положенная до попытки, и запись после дают в ленте одну и ту же
    строку, и отличить их можно только этим вопросом.
    """

    def __init__(self, tape: Tape, falls: bool = False, **rest: Any) -> None:
        super().__init__(**rest)
        self.tape = tape
        self.falls = falls
        self.told: list[int] = []

    def _restart_app(self) -> None:
        self.told.append(len(self.tape.named("reload")))
        if self.falls:
            raise OSError("приёмник ушёл")


def _watched(tape: Tape, falls: bool = False) -> _Watched:
    """Молчащий приёмник, у которого повтор LOAD идёт под присмотром ленты."""
    device = Device()
    device.media_controller = _Loading(Status(state="IDLE", idle_reason="ERROR"))  # type: ignore[assignment]
    made = _Watched(tape, falls, device=device, clock=FakeClock())
    made._url, made._title = "http://дом/поток.m3u8", "Моана"
    return made


def test_the_feed_counts_retries_that_happened_and_not_retries_that_were_promised(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 Сторож ловит ПОРЯДОК записи, а не её наличие.

    Запись, положенная в ленту ДО попытки, - обещание, и снять его было нечем. У двух
    порядков числа тут разные, а любая проверка «строка в ленте есть» покупается обоими.
    """
    receiver = _watched(tape)

    assert receiver._settle(600.0) is False

    limit = receiver.profile.load_retries
    assert receiver.told == list(range(limit)), "лента знала о повторе раньше самого повтора"
    assert len(tape.named("reload")) == limit
    assert all(row["ok"] is True for row in tape.named("reload")), "повторы ушли - так и записано"
    assert "LOAD was not taken" in capsys.readouterr().out


def test_a_retry_that_fell_inside_the_wait_is_named_and_still_goes_up(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """Исключение уходит наверх как уходило, но обещание повтора снимается тем же заходом.

    🔴 Замер на стенде 30-08-2026 давал ровно эту пару: ``{"event": "reload", "tries": 1,
    "error": null}`` в ленте и «ТВ не принял каст» текстом ошибки процесса рядом. По ленте
    повтор числился ушедшим, хотя не ушёл, и причину приходилось читать НЕ в ленте.
    """
    receiver = _watched(tape, falls=True)

    with pytest.raises(OSError, match="приёмник ушёл"):
        receiver._settle(600.0)

    (record,) = tape.named("reload")
    assert record["ok"] is False, "легший повтор не смеет звать себя ушедшим"
    assert str(record["why"]).startswith("crashed:"), f"чужое слово: {record}"
    assert "LOAD was not taken" in capsys.readouterr().out


def test_a_paused_load_asks_the_receiver_not_to_start() -> None:
    """LOAD без автостарта: сессия на закладке ждёт зрителя, снявшего паузу с пульта."""
    receiver = _receiver()

    receiver._load(2231.0, paused=True)

    controller = receiver.device.media_controller
    assert isinstance(controller, _Loading)
    (load,) = controller.loads
    assert load["autoplay"] is False
    assert load["current_time"] == 2231.0


def test_a_paused_load_settles_on_the_paused_word() -> None:
    """Готовность LOAD без автостарта - слово PAUSED, а не картинка на экране."""
    clock = FakeClock()
    receiver = _receiver(Status(state="PAUSED"), clock=clock)
    receiver._load(2231.0, paused=True)

    assert receiver._settle(60.0) is True


def test_a_receiver_that_ignored_autoplay_is_paused_back() -> None:
    """Приёмник не удержал LOAD без старта и начал сам - паузу зрителя возвращаем мы."""
    clock = FakeClock()
    receiver = _receiver(Status(state="PLAYING"), clock=clock)
    receiver._load(2231.0, paused=True)

    assert receiver._settle(60.0) is True
    controller = receiver.device.media_controller
    assert isinstance(controller, _Loading)
    assert controller.said == ["pause"], "одна команда паузы - и показ снова ждёт зрителя"


def test_a_budget_that_ran_out_ends_the_wait_without_a_single_retry() -> None:
    """Бюджет кончился - показ не начался, и лишних LOAD в приёмник не уходит."""
    clock = FakeClock()
    receiver = _receiver(Status(state="IDLE"), clock=clock)

    assert receiver._settle(0.0) is False
    assert receiver._reloads == 0
