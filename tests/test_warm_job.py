"""Прогретая запись узнаётся по файлу и секунде закладки."""

from web.warm_job import WarmJob


def test_a_moved_bookmark_is_a_new_job_and_a_fraction_of_a_second_is_not() -> None:
    job = WarmJob("magnet:a", "http://торрент/0", 600.2, "a.mkv")

    assert job.mark == WarmJob("magnet:a", "http://торрент/0", 599.9, "a.mkv").mark
    assert job.mark != WarmJob("magnet:a", "http://торрент/0", 900.0, "a.mkv").mark
    assert job.mark != WarmJob("magnet:a", "http://торрент/1", 600.2, "a.mkv").mark
