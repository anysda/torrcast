"""Профиль приёмника: пороги выбираются по паспорту устройства, а не прибиты к одному ТВ.

Проверяется ровно то, ради чего профиль заводился: незнакомый приёмник получает
осторожный набор (а не смелый), знакомая приставка - свой, названное руками сильнее
паспорта, а на Q70D всё остаётся ровно тем же, чем было.
"""

from __future__ import annotations

import dataclasses
import time
from typing import ClassVar

import pytest

from torrcast import cast, profile, stream
from torrcast.state import Config


def test_the_stock_config_is_the_cautious_profile() -> None:
    """Умолчания настроек и осторожный профиль - одно и то же число, а не два похожих.

    Это и есть главный критерий приёмки карточки: пока конфиг молчит, показ обязан вести
    себя ровно как до профилей. Разойдись эти два места хоть на знак - на Q70D поехали бы
    другие пороги, и никто бы этого не заметил до первого подвиса.
    """
    stock = Config()
    cautious = profile.CAUTIOUS
    assert stock.hls_segment == cautious.segment_seconds == 10.0
    assert stock.hls_burst == cautious.burst == 60.0
    assert stock.bitrate_warn_mbit == cautious.warn_mbit == 16.0
    assert stock.recode_at_mbit == cautious.recode_at_mbit == 10.0
    assert stock.recode_mbit == cautious.recode_mbit == 9.0


def test_the_stream_constants_are_the_cautious_profile() -> None:
    """Константы упаковки - тот же осторожный профиль, а не своя копия чисел."""
    cautious = profile.CAUTIOUS
    assert stream.MAX_SEGMENT_BYTES == cautious.max_segment_bytes == 16_000_000
    assert stream.RECODE_CODECS == cautious.recode_codecs == frozenset({"hevc"})
    assert stream.COPY_DEPTH == cautious.copy_depth == 8
    assert dataclasses.fields(stream.Feed)  # slots-датакласс: умолчание берём из поля
    holds = {f.name: f.default for f in dataclasses.fields(stream.Feed)}
    assert holds["wait"] == cautious.hold_seconds == 120.0
    assert holds["burst"] == cautious.burst == 60.0
    assert cast.MockReceiver.PATIENCE == cautious.patience == 23.5
    assert cast.MockReceiver.SULK == cautious.sulk == 0.0
    assert cast.MockReceiver.SEGMENT_RETRIES == cautious.segment_retries == 2
    assert cast.ChromecastReceiver.REVIVE_TIMEOUT == cautious.revive_timeout == 300.0


def test_the_revival_waits_are_the_cautious_profile() -> None:
    """Обе выдержки воскрешения - из профиля приёмника, и они про РАЗНОЕ.

    :attr:`torrcast.profile.Profile.revive_drop` - через сколько приёмник снова берёт LOAD
    (замер: 3-4 с), :attr:`torrcast.profile.Profile.revive_pause` - как редко жечь
    оставшиеся попытки, чтобы их хватило на всё окно возврата. Сложи их в одно число - и
    темнота по вине приёмника снова станет минутой чёрного экрана впустую.
    """
    from torrcast import cli

    cautious = profile.CAUTIOUS
    assert cli.REVIVE_PAUSE == cautious.revive_pause == 60.0
    assert cli.REVIVE_DROP == cautious.revive_drop == 4.0
    assert cautious.revive_drop < cautious.revive_pause, "приёмника ждут секунды, а не минуту"


@pytest.mark.parametrize(
    "maker,model,name",
    [
        ("Samsung", "", "Samsung Q70D"),
        ("", "", ""),  # приёмник не представился вовсе
        ("Sony", "BRAVIA", "Гостиная"),  # чужое железо, которого мы не мерили
        ("Google Inc.", "Chromecast Ultra", "Спальня"),
    ],
)
def test_an_unknown_receiver_gets_the_cautious_profile(maker: str, model: str, name: str) -> None:
    """🔴 Незнакомая модель получает САМЫЙ ОСТОРОЖНЫЙ набор, а не самый смелый.

    Наоборот было бы не «оптимистично», а сломано: на чужом декодере смелые пороги дают
    вечную петлю LOAD/BUFFERING вместо картинки, и разбираться в ней человеку нечем.
    Chromecast Ultra в списке нарочно: он ближайший родственник измеренной приставки, и
    похожесть тут не довод - профиль даётся за замер, а не за фамилию.
    """
    assert profile.for_passport(maker, model, name) is profile.CAUTIOUS


def test_the_android_stick_is_recognised_by_its_maker_alone() -> None:
    """Приставка узнаётся по производителю: имя и модель она отдаёт пустыми (замер)."""
    assert profile.for_passport("Xiaomi", "", "") is profile.ANDROID_TV


def test_the_stick_is_bold_only_where_it_was_measured() -> None:
    """Смелое у приставки - только то, что замер называет прямо.

    Замер 09-08-2026: 28 Мбит/с CBR прошли начисто (потолок Q70D около 10), после 404
    обиды нет - следующий LOAD взят через 8.9 с, пустой экран приставка терпит дольше
    577 с (оба прогона обрывал наблюдатель, верхняя граница не найдена, приложение само
    с экрана не уходит). Про вес куска, шаг сетки и пороги сторожа нуджей замер не
    говорит НИЧЕГО, а HEVC через наш mpegts на ней ещё не проходил - значит, эти пороги
    обязаны остаться осторожными.
    """
    stick, cautious = profile.ANDROID_TV, profile.CAUTIOUS
    assert stick.warn_mbit > cautious.warn_mbit and stick.recode_at_mbit > cautious.recode_at_mbit
    assert stick.segment_retries == 0, "приставка кусок не перезабирает - замер"
    assert stick.dead_url_seconds == 4.0, "мёртвый URL - IDLE/ERROR на 4-й секунде, замер"
    assert stick.patience == 577.0 > cautious.patience, "нижняя граница, верхняя не найдена"
    assert stick.app_patience == 577.0, "приложение висело на экране весь прогон голодания"
    assert stick.hold_seconds == cautious.hold_seconds == 120.0, "120 с тишины терпит с запасом"
    assert stick.revive_timeout == 577.0 > cautious.revive_timeout, "окно возврата - та же граница"
    assert stick.revive_pause == 10.0, "LOAD после IDLE/ERROR взят через 8.9 с - замер"
    assert stick.revive_drop == 10.0 > cautious.revive_drop, (
        "приставке проворность не выдумываем: раньше 8.9 с к LOAD она не возвращалась"
    )
    assert stick.recode_codecs == cautious.recode_codecs, "HEVC в нашем mpegts ещё не проверен"
    assert stick.copy_depth == cautious.copy_depth, "Hi10P в нашем mpegts ещё не проверен"
    assert stick.max_segment_bytes == cautious.max_segment_bytes, "вес куска не измеряли"
    assert stick.segment_seconds == cautious.segment_seconds, "шаг сетки не измеряли"
    assert (stick.stall_seconds, stick.ready_ahead, stick.stall_skip) == (
        cautious.stall_seconds,
        cautious.ready_ahead,
        cautious.stall_skip,
    ), "сторож нуджей замером не назван"
    assert stick.load_retries == cautious.load_retries, "свои повторы LOAD замер не отменяет"


def test_a_named_profile_beats_the_passport() -> None:
    """Ручное переопределение работает и не спрашивает устройство вовсе.

    Ключ в настройках - последнее слово: приёмник может врать паспортом, а пороги уже
    известны. Опрос при этом не делается ни одного - иначе выключенный ТВ стоил бы
    секунд там, где человек всё сказал сам.
    """
    profile.forget()
    asked: list[str] = []
    chosen = profile.detect(Config(tv="10.0.0.50", receiver_profile="androidtv"))
    assert chosen.profile is profile.ANDROID_TV
    assert "руками" in chosen.how and not asked


def test_an_unknown_name_in_the_config_is_not_a_crash() -> None:
    """Опечатка в ``receiver_profile`` - осторожный профиль и честная строка, а не отказ."""
    chosen = profile.detect(Config(tv="10.0.0.50", receiver_profile="q70"))
    assert chosen.profile is profile.CAUTIOUS and "q70" in chosen.how


def test_without_an_address_nobody_is_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Заглушка и показ без адреса ТВ паспорт не спрашивают: спрашивать не у кого."""
    profile.forget()

    def refuse(address: str, timeout: float = 0.0) -> None:
        raise AssertionError("паспорт спрашивать было не у кого")

    monkeypatch.setattr("torrcast.scan.named", refuse)
    assert profile.detect(Config()).profile is profile.CAUTIOUS
    assert profile.detect(Config(tv="mock", receiver="mock")).profile is profile.CAUTIOUS


def test_the_passport_is_asked_once_per_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """Паспорт спрашивается один раз на процесс: показ зовёт профиль в нескольких местах."""
    from torrcast.scan import Device

    profile.forget()
    asked: list[str] = []

    def once(address: str, timeout: float = 0.0) -> Device:
        asked.append(address)
        return Device(address=address, maker="Xiaomi")

    monkeypatch.setattr("torrcast.scan.named", once)
    config = Config(tv="10.0.0.50")
    assert profile.detect(config).profile is profile.ANDROID_TV
    assert profile.detect(config).profile is profile.ANDROID_TV
    assert asked == ["10.0.0.50"], "второй раз устройство не дёргаем"
    profile.forget()


def test_a_silent_receiver_gets_the_cautious_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Приёмник не ответил (спит, сети нет) - осторожный профиль, а не авария показа."""
    profile.forget()

    def dead(address: str, timeout: float = 0.0) -> None:
        raise OSError("сети нет")

    monkeypatch.setattr("torrcast.scan.named", dead)
    chosen = profile.detect(Config(tv="10.0.0.50"))
    assert chosen.profile is profile.CAUTIOUS and "не ответил" in chosen.how
    profile.forget()


def test_the_profile_moves_the_config_thresholds() -> None:
    """Профиль перебивает умолчания настроек - те, у которых есть свой ключ в конфиге."""
    tuned = profile.tune(Config(), profile.ANDROID_TV)
    assert tuned.bitrate_warn_mbit == profile.ANDROID_TV.warn_mbit == 28.0
    assert tuned.recode_at_mbit == profile.ANDROID_TV.recode_at_mbit == 28.0
    assert profile.tune(Config(), profile.CAUTIOUS) == Config(), "осторожный ничего не меняет"


def test_a_hand_written_setting_beats_the_profile() -> None:
    """Написанное в конфиг руками сильнее профиля: иначе настройку было бы не удержать."""
    mine = Config(bitrate_warn_mbit=12.0, recode_at_mbit=7.0)
    tuned = profile.tune(mine, profile.ANDROID_TV)
    assert (tuned.bitrate_warn_mbit, tuned.recode_at_mbit) == (12.0, 7.0)


def test_the_receiver_takes_its_thresholds_from_the_profile() -> None:
    """Пороги приёмника едут из профиля, а не из констант класса.

    Проверка именно на объекте: класс держит осторожные числа умолчанием, и легко было бы
    оставить показ читать их напрямую - тогда профиль не менял бы ровно ничего.
    """
    stick = cast.ChromecastReceiver("10.0.0.50", profile=profile.ANDROID_TV)
    assert stick.profile.revive_timeout == 577.0 != cast.ChromecastReceiver.REVIVE_TIMEOUT
    mock = cast.MockReceiver(profile=profile.ANDROID_TV)
    assert mock.patience == profile.ANDROID_TV.patience
    assert mock.profile.segment_retries == 0 != cast.MockReceiver.SEGMENT_RETRIES
    assert mock.profile.sulk == 0.0, "приставка на 404 не обижается - замер"


def test_the_codec_verdict_follows_the_profile() -> None:
    """«Играем только h264» - тоже свойство приёмника, а не показа."""
    assert stream.recodes_whole("hevc", 8, profile.CAUTIOUS)
    assert stream.recodes_whole("h264", 10, profile.CAUTIOUS), "Hi10P Q70D не берёт"
    assert not stream.recodes_whole("h264", 8, profile.CAUTIOUS)
    assert profile.CAUTIOUS.plays_copy("h264") and not profile.CAUTIOUS.plays_copy("av1")
    assert profile.CAUTIOUS.plays_copy(""), "паспорта нет - играем копией, как прежде"


@pytest.mark.parametrize(
    "codec,depth,want",
    [
        ("h264", 8, profile.COPY),
        ("h264", 0, profile.COPY),
        ("", 0, profile.COPY),  # запись прежней версии: кодека не спрашивали
        ("h264", 10, profile.RECODE),  # Hi10P зовётся тем же именем
        ("hevc", 8, profile.RECODE),
        ("hevc", 10, profile.RECODE),
        ("vp9", 0, profile.REFUSE),
        ("av1", 0, profile.REFUSE),
        ("vc1", 0, profile.REFUSE),
        ("mpeg2video", 0, profile.REFUSE),
    ],
)
def test_the_verdict_is_the_only_place_where_a_codec_is_judged(
    codec: str, depth: int, want: str
) -> None:
    """🔴 Судьба картинки решается одним вызовом: копия, сплошной перекод или отказ.

    Раньше ответов было два разных в двух местах - белый список копии на отборе и чёрный
    список перекода в упаковке, - и между ними была щель ровно в размер VP9.
    """
    assert profile.CAUTIOUS.verdict(codec, depth) == want
    assert profile.ANDROID_TV.verdict(codec, depth) == want, "замер на приставке был нативный"


@pytest.mark.parametrize("codec", ["vp9", "av1", "vc1", "mpeg2video"])
def test_an_unmeasured_codec_never_leaves_for_the_receiver_as_a_copy(codec: str) -> None:
    """🔴 То, чего приёмник не играет по HLS, копией не уезжает НИКОГДА.

    Тот самый дефект: отбор VP9 отбраковывал, а упаковка про него не знала вовсе -
    список перекодируемых кодеков был чёрным и состоял из одного ``hevc``. Раздача,
    названная руками (``--release N``) или поднятая из записи возобновления, доезжала до
    упаковки и получала ``-c:v copy`` в mpegts: приёмник такой показ не начинает вовсе.
    AV1 при этом спасала отбраковка на отборе, VP9 не спасало ничто.
    """
    from torrcast.cli import _encode_all
    from torrcast.state import Config

    assert stream.recodes_whole(codec, 0, profile.CAUTIOUS), "копией такое не отдаём"
    assert _encode_all(Config(), codec, profile=profile.CAUTIOUS) is not None
    assert not stream.Media(video=codec).video_warning.startswith("внимание: видео h264")
    assert stream.Media(video=codec, duration=1.0).recoded_whole, "ключ прогретого тот же"


def test_the_hevc_path_is_untouched_and_plain_h264_still_goes_as_a_copy() -> None:
    """Гейт обратной стороны: закрытому пути HEVC от белого списка ни жарко ни холодно."""
    from torrcast.cli import _encode_all
    from torrcast.state import Config

    assert _encode_all(Config(), "hevc", profile=profile.CAUTIOUS) is not None
    assert _encode_all(Config(), "h264", depth=10, profile=profile.CAUTIOUS) is not None
    assert _encode_all(Config(), "h264", depth=8, profile=profile.CAUTIOUS) is None
    assert _encode_all(Config(), "", profile=profile.CAUTIOUS) is None
    assert not stream.recodes_whole("h264", 8, profile.CAUTIOUS)


class _FakeDevice:
    """Приёмник, который только и умеет, что записать, куда его попросили прыгнуть."""

    def __init__(self, jumps: list[float]) -> None:
        self.media_controller = self
        self.jumps = jumps

    def seek(self, pos: float) -> None:
        self.jumps.append(pos)


def test_the_watchdog_jumps_by_the_profile_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сторож подвиса меряет и терпение, и шаг прыжка ПРОФИЛЕМ, а не константой класса.

    Проверка живая, а не «поле на месте»: константы класса остались осторожными
    умолчаниями, и код, читающий их напрямую, выглядел бы рабочим ровно до второго
    приёмника - на нём профиль не менял бы ничего.
    """
    mine = dataclasses.replace(profile.CAUTIOUS, stall_seconds=30.0, stall_skip=25.0)
    jumps: list[float] = []
    monkeypatch.setattr(cast.ChromecastReceiver, "_device", lambda self: _FakeDevice(jumps))
    receiver = cast.ChromecastReceiver("10.0.0.50", profile=mine)
    receiver._peak = 84.0

    receiver._nudge(84.0, front=144.0)
    receiver._stall_since -= cast.ChromecastReceiver.STALL_SECONDS  # осторожные 8 с
    receiver._nudge(84.0, front=144.0)
    assert jumps == [], "терпение сторожа - профильные 30 с, а не 8 с класса"

    receiver._stall_since -= mine.stall_seconds
    receiver._nudge(84.0, front=144.0)
    assert jumps == [84.0 + mine.stall_skip], "и шаг прыжка тоже профильный"


def test_the_mock_receiver_sulks_by_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """404 наказывает столько, сколько сказано в профиле, - а замер говорит «нисколько».

    Наказание было прибито к Q70D числом 150 с; замер 09-08-2026 снял его трижды двумя
    независимыми каналами - и на Q70D, и на приставке. Модель обязана держаться замера:
    заглушка, наказывающая за 404, объявляла бы мёртвым показ, который живьём поднимается
    с первой попытки. Механизм при этом жив - наказание ставится числом профиля.
    """

    class _Answer:
        status_code = 404
        headers: ClassVar[dict[str, str]] = {}

    stick = cast.MockReceiver(profile=profile.ANDROID_TV)
    stick._caught(_Answer())
    assert stick._sulk <= time.monotonic(), "приставка на 404 не обижается - LOAD берётся сразу"

    q70d = cast.MockReceiver()
    q70d._caught(_Answer())
    assert q70d._sulk <= time.monotonic(), "и Q70D тоже: замер 09-08 снял наказание трижды"

    sulky = cast.MockReceiver(profile=dataclasses.replace(profile.CAUTIOUS, sulk=150.0))
    sulky._caught(_Answer())
    assert sulky._sulk - time.monotonic() > 100.0, "механизм жив: наказание ставится числом"
