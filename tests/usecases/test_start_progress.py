"""Зеркало хода подъёма: что экран ожидания узнаёт о сроке и о чём молчит."""

from __future__ import annotations

from torrcast.usecases.start_progress import ENOUGH, KEPT, StartProgress


class Ticker:
    """Часы под рукой: подъём меряется временем, и время тут задаётся, а не ждётся."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _lift(progress: StartProgress, tick: Ticker, seconds: float) -> None:
    """Подъём, дошедший до экрана за ``seconds``: ровно так он попадает в память."""
    progress.began()
    tick.now += seconds
    progress.landed()


def _left(progress: StartProgress) -> object:
    """Названный срок идущего подъёма: другого окна в память замеров у зрителя нет."""
    seen = progress.seen()
    assert seen is not None
    return seen["left"]


def test_nothing_is_lifting_so_the_screen_hears_nothing() -> None:
    assert StartProgress(Ticker()).seen() is None


def test_first_lift_says_how_long_we_wait_and_keeps_silent_about_the_term() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    progress.began()
    tick.now += 7.4
    seen = progress.seen()
    assert seen == {"waited": 7.4, "left": None, "source": None, "sources": None}


def test_source_of_the_queue_is_named_with_its_number_and_total() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    progress.began()
    progress.source(2, 5)
    seen = progress.seen()
    assert seen is not None
    assert (seen["source"], seen["sources"]) == (2, 5)


def test_term_comes_from_measured_lifts_not_from_a_budget() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    for measured in (40.0, 60.0, 50.0):
        _lift(progress, tick, measured)
    # Середина трёх замеров - 50 с, и ровно её остаток идёт наружу.
    progress.began()
    tick.now += 20.0
    seen = progress.seen()
    assert seen is not None
    assert (seen["waited"], seen["left"]) == (20.0, 30)


def test_expired_term_says_i_do_not_know_instead_of_zero() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    for measured in (30.0, 30.0):
        _lift(progress, tick, measured)
    progress.began()
    tick.now += 45.0
    seen = progress.seen()
    assert seen is not None
    assert seen["left"] is None
    assert seen["waited"] == 45.0


def test_picture_arrived_so_the_waiting_is_over() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    progress.began()
    progress.source(1, 3)
    tick.now += 28.0
    progress.landed()
    assert progress.seen() is None
    # Опрос идущего показа повторяется каждые две секунды, и второй кадр того же
    # подъёма памяти замеров сказать уже нечего.
    progress.landed()
    assert progress.seen() is None


def test_lift_fell_apart_and_nothing_gets_measured() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    for measured in (30.0, 30.0):
        _lift(progress, tick, measured)
    progress.began()
    progress.gone()
    assert progress.seen() is None
    # Развалившийся подъём в память сроков не пошёл: следующий зовётся тем же числом.
    progress.began()
    assert _left(progress) == 30


def test_memory_holds_one_evening_not_the_whole_history() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    for measured in range(1, KEPT + 4):
        _lift(progress, tick, float(measured))
    # Первые три замера вытеснены: осталось 4..8, и середина у них - 6, а не 4.
    progress.began()
    assert _left(progress) == 6


def test_a_single_measured_lift_is_a_case_and_not_a_term() -> None:
    tick = Ticker()
    progress = StartProgress(tick)
    for _ in range(ENOUGH - 1):
        _lift(progress, tick, 56.0)
    progress.began()
    # Один замер - это случай, а не разброс: живой прогон назвал бы по нему «~56 с» там,
    # где картинка пришла за 20 с. Срока нет, и страница о нём молчит.
    assert _left(progress) is None
    progress.gone()
    _lift(progress, tick, 24.0)
    progress.began()
    # Замеров стало достаточно: наружу идёт их середина.
    assert _left(progress) == 40
