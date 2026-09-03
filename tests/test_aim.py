"""Зеркало места: ползунок уезжает туда, куда его поставили, а возвращает его правда."""

from __future__ import annotations

from hass.aim import LANDED_SECONDS, Aim
from torrcast.domain.playback_snapshot import PlaybackSnapshot


class _Clock:
    """Часы теста: время идёт ровно туда, куда его двигают."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _shown(position: float, key: str = "movie:муха", paused: str = "") -> PlaybackSnapshot:
    return PlaybackSnapshot(
        key=key, title="Муха", position=position, duration=3600.0, moved=True, paused=paused
    )


def _place(aim: Aim, shown: PlaybackSnapshot) -> float:
    """Позиция снимка, каким его увидит карточка."""
    answered = aim.seen(shown)
    assert answered is not None
    return answered.position


def test_a_bookmark_nobody_moved_is_handed_over_untouched() -> None:
    """Без собственной команды моста выдумывать нечего: правда как есть."""
    aim = Aim(clock=_Clock())

    assert _place(aim, _shown(60.0)) == 60.0


def test_the_slider_stands_where_it_was_dropped_on_the_very_next_poll() -> None:
    """🔴 То, ради чего защёлка и заведена.

    Home Assistant переспрашивает состояние сразу после команды, и на том опросе запись
    показа несёт ещё СТАРОЕ место: приёмник перемотку только берёт, а сторож положит
    закладку на диск лишь на своём тике. Ответить правдой значило отбросить ползунок
    туда, откуда его только что утащили.
    """
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(2488.0))
    aim.at(600.0)

    assert _place(aim, _shown(2488.0)) == 3088.0


def test_the_slider_keeps_running_forward_under_the_latch() -> None:
    """Показ едет и под защёлкой, иначе каждый опрос отбрасывал бы ползунок назад.

    Метка позиции у каждого ответа своя (``media_position_updated_at`` - время опроса),
    и фронт доводит ползунок от неё сам. Ответить дважды одним и тем же числом с разными
    метками - это и есть отскок на весь промежуток между опросами.
    """
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(2488.0))
    aim.at(600.0)
    clock.now = 5.0

    assert _place(aim, _shown(2488.0)) == 3093.0


def test_a_paused_show_does_not_run_forward_under_the_latch() -> None:
    """Перемотка на паузе: место названо, а времени под ним не идёт."""
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(2488.0, paused="PAUSED"))
    aim.at(600.0)
    clock.now = 5.0

    assert _place(aim, _shown(2488.0, paused="PAUSED")) == 3088.0


def test_the_latch_is_lifted_by_the_record_catching_up() -> None:
    """Защёлку снимает ФАКТ: запись назвала место у цели - дальше врать незачем."""
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(2488.0))
    aim.at(600.0)
    clock.now = 9.0

    assert _place(aim, _shown(3095.0)) == 3095.0
    #: И назад к выдумке не возвращается: защёлка снята насовсем, а не на один опрос.
    clock.now = 11.0
    assert _place(aim, _shown(3097.0)) == 3097.0


def test_a_seek_the_receiver_never_took_gives_the_slider_back_to_the_truth() -> None:
    """Окно вышло, а закладка стоит там же - приёмник команду не взял.

    Залипнуть навсегда ползунок не имеет права: человек смотрит на число, которого на
    экране нет.
    """
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(2488.0))
    aim.at(600.0)
    clock.now = LANDED_SECONDS - 0.1
    assert _place(aim, _shown(2490.0)) > 3000.0

    clock.now = LANDED_SECONDS
    assert _place(aim, _shown(2492.0)) == 2492.0


def test_another_show_does_not_inherit_the_latch() -> None:
    """Сменился показ - оптимизма нет: место чужой картины к цели отношения не имеет."""
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(2488.0))
    aim.at(600.0)
    clock.now = 1.0

    assert _place(aim, _shown(12.0, key="movie:тачки")) == 12.0


def test_a_rewind_to_the_beginning_is_aimed_at_zero_and_not_below() -> None:
    """«Сначала» с карточки - сдвиг в минус на всю позицию; ниже нуля оси нет."""
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(2488.0))
    aim.at(-2488.0)

    assert _place(aim, _shown(2488.0)) == 0.0


def test_a_seek_aims_from_the_place_the_card_was_showing() -> None:
    """Сдвиг Home Assistant считает от позиции снимка - от неё же собирается и цель.

    Запись между опросом и командой не двигалась: сторож пишет реже, чем человек тянет
    ползунок. Цель обязана совпасть с точкой, куда его отпустили, а не с суммой сдвига и
    какого-нибудь другого места.
    """
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(1000.0))
    _place(aim, _shown(1000.0))
    aim.at(-300.0)  # человек утащил ползунок с 1000 на 700

    assert _place(aim, _shown(1000.0)) == 700.0
