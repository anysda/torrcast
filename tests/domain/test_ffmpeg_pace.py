"""Зеркало :mod:`torrcast.domain.ffmpeg_pace`."""

from torrcast.domain.ffmpeg_pace import PACE_MARGIN_SECONDS, FfmpegPace


def test_pace_within_the_margin_of_the_baseline_is_honored() -> None:
    """Секунды честной сборки лежат далеко внутри допуска - на упор проверять нечего."""
    pace = FfmpegPace(baseline_seconds=0.1, burst_seconds=0.13, entry_seconds=0.09)
    assert pace.burst_honored is True
    assert pace.entry_paced is True


def test_burst_costing_the_whole_window_is_inert() -> None:
    """TC-1048: 7.7 с burst-чтения из 8 заказанных - это чтение без темпа вовсе."""
    pace = FfmpegPace(baseline_seconds=0.08, burst_seconds=7.74, entry_seconds=0.09)
    assert pace.burst_honored is False
    assert pace.entry_paced is True


def test_entry_costing_the_distance_to_it_is_paced_from_the_start() -> None:
    """TC-1048: посадка на 10-й секунде ждёт 11.47 с - темп посчитан от начала файла."""
    pace = FfmpegPace(baseline_seconds=0.08, burst_seconds=0.1, entry_seconds=11.47)
    assert pace.burst_honored is True
    assert pace.entry_paced is False


def test_the_margin_is_the_exact_line_between_honored_and_not() -> None:
    """Граница допуска не сдвигается тихо: ровно на нём - ещё честно, шагом дальше - нет."""
    edge = FfmpegPace(baseline_seconds=0.0, burst_seconds=PACE_MARGIN_SECONDS, entry_seconds=0.0)
    assert edge.burst_honored is True
    over = FfmpegPace(
        baseline_seconds=0.0, burst_seconds=PACE_MARGIN_SECONDS + 0.01, entry_seconds=0.0
    )
    assert over.burst_honored is False
