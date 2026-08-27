from scripts.seekgaps import Landing, _demux_error, boundaries, summary


def test_the_probe_asks_every_nonzero_uniform_boundary() -> None:
    assert boundaries(35.001, 10.0) == [10.0, 20.0, 30.0]
    assert boundaries(34.999, 10.0) == [10.0, 20.0]


def test_a_zero_exit_demux_error_is_still_an_error() -> None:
    assert _demux_error("Error during demuxing: Input/output error")


def test_the_widest_gap_is_between_distinct_reachable_landings() -> None:
    rows = [
        Landing(10.0, 4.0, 1),
        Landing(20.0, 4.0, 1),
        Landing(30.0, 92.0, 1),
        Landing(40.0, None, 3, "рой не ответил"),
    ]

    report = summary(rows, 45.0, 10.0)

    assert report["самый широкий провал"] == 88.0
    assert report["между"] == [4.0, 92.0]
    assert report["шире 80 с"] is True
    assert report["недоступные границы"] == [40.0]
