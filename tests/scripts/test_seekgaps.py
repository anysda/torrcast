from scripts.seekgaps import (
    AT_ONCE,
    GAVE_UP,
    SETTLED,
    UNMEASURED,
    Outcome,
    Pilot,
    UnreachableError,
    _run_error,
    boundaries,
    outcome,
    summary,
    widest,
)


class _Silent(Pilot):
    """Измеритель, у которого ни одно место не читается: граница остаётся неизмеренной."""

    def __call__(self, url: str, at: float, timeout: float, keys: object = None) -> float:
        self.asks += 1
        raise UnreachableError("рой не ответил")


def _remembering(seen: dict[float, float]) -> Pilot:
    """Измеритель, которому все места уже известны: ffmpeg он не поднимает ни разу."""
    return Pilot("url", 1.0, seen=dict(seen))


def test_the_probe_asks_every_nonzero_uniform_boundary() -> None:
    assert boundaries(35.001, 10.0) == [10.0, 20.0, 30.0]
    assert boundaries(34.999, 10.0) == [10.0, 20.0]


def test_a_zero_exit_demux_error_is_still_an_error() -> None:
    assert _run_error("Error during demuxing: Input/output error")


def test_a_muxer_refusing_a_stream_without_stamps_is_also_an_error() -> None:
    assert _run_error("[mpegts @ 0x1] first pts and dts value must be set")
    assert _run_error("[out#0/mpegts @ 0x1] Error muxing a packet")
    assert not _run_error("frame= 1 fps=0.0 q=-1.0 size=1kB")


def test_a_start_landing_before_the_boundary_costs_one_run() -> None:
    pilot = _remembering({200.0: 196.0})

    got = outcome(pilot, 200.0, extra=2)

    assert got.kind == AT_ONCE
    assert got.asked == 1
    assert pilot.runs == 0


def test_a_start_landing_late_is_pulled_back_behind_the_boundary() -> None:
    pilot = _remembering({100.0: 112.0, 88.0: 95.0})

    got = outcome(pilot, 100.0, extra=2)

    assert got.kind == SETTLED
    assert (got.stood, got.settled) == (112.0, 95.0)
    assert got.asked == 2


def test_the_rule_gives_up_and_the_probe_prices_the_step_that_would_have_saved_it() -> None:
    # Отвод удваивается с уезда 15 с: 4985, 4970, 4940, 4880 - все они дают то же место.
    stuck = dict.fromkeys((5000.0, 4985.0, 4970.0, 4940.0, 4880.0), 5015.0)
    pilot = _remembering({**stuck, 4760.0: 4700.0})

    got = outcome(pilot, 5000.0, extra=2)

    assert got.kind == GAVE_UP
    assert got.settled == 5015.0
    # Пятый шаг отводит на 240 с и накрывает границу: цена поднятого потолка названа.
    assert got.rescued == 5
    assert got.asked == 6


def test_a_boundary_nobody_can_measure_is_not_counted_as_a_landing() -> None:
    got = outcome(_Silent("url", 1.0), 300.0, extra=2)

    assert got.kind == UNMEASURED
    assert got.stood is None
    assert got.error == "рой не ответил"


def test_the_widest_gap_is_between_distinct_reachable_landings() -> None:
    rows = [
        Outcome(10.0, 4.0, 4.0, 1, AT_ONCE),
        Outcome(20.0, 4.0, 4.0, 1, AT_ONCE),
        Outcome(30.0, 92.0, 92.0, 5, GAVE_UP),
    ]

    assert widest(rows) == (4.0, 92.0, 88.0)


def test_the_report_counts_every_verdict_and_both_prices() -> None:
    rows = [
        Outcome(10.0, 4.0, 4.0, 1, AT_ONCE),
        Outcome(20.0, 26.0, 18.0, 2, SETTLED),
        Outcome(30.0, 92.0, 92.0, 6, GAVE_UP, rescued=5),
        Outcome(40.0, None, None, 1, UNMEASURED, error="рой не ответил"),
    ]
    pilot = _remembering({})
    pilot.asks, pilot.runs = 10, 7

    report = summary(rows, pilot, 45.0, 10.0)

    assert (report["сразу"], report["отведён"], report["сдался"]) == (1, 1, 1)
    assert report[UNMEASURED] == 1
    assert report["границы сдачи"] == [30.0]
    assert report["спасли бы шагом"] == [5]
    # Посадки 4, 26 и 92: широчайший провал считается между СОСЕДНИМИ из них, а не с краю.
    assert report["самый широкий провал"] == 66.0
    assert report["шире 80 с"] is False
    assert (report["спрошено правилом"], report["прогонов ffmpeg"]) == (10, 7)
