"""Прогретая запись узнаётся по файлу и секунде закладки."""

from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain.entry import Entry
from torrcast.domain.torr_file import TorrFile
from web.warm_job import WarmJob


def test_a_moved_bookmark_is_a_new_job_and_a_fraction_of_a_second_is_not() -> None:
    job = WarmJob("magnet:a", "http://торрент/0", 600.2, "a.mkv")

    assert job.mark == WarmJob("magnet:a", "http://торрент/0", 599.9, "a.mkv").mark
    assert job.mark != WarmJob("magnet:a", "http://торрент/0", 900.0, "a.mkv").mark
    assert job.mark != WarmJob("magnet:a", "http://торрент/1", 600.2, "a.mkv").mark


def test_the_job_of_a_record_is_its_file_at_its_bookmark() -> None:
    engine = FakeTorrentEngine(torrent_files=[TorrFile(0, "s01e01.mkv"), TorrFile(1, "s01e02.mkv")])
    entry = Entry(title="Рик", magnet="magnet:a", pos=660.0, dur=1300.0, file_idx=1)

    job = WarmJob.of(engine, entry, "hash")

    assert job == WarmJob("magnet:a", "http://fake/hash/1", 660.0, "s01e02.mkv")


def test_no_metadata_or_no_name_of_the_file_is_no_job() -> None:
    """Пустое имя грело бы раздачу, о которой служба ещё ничего не знает, наугад."""
    entry = Entry(title="Рик", magnet="magnet:a", pos=660.0, dur=1300.0, file_idx=1)

    assert WarmJob.of(FakeTorrentEngine(), entry, "hash") is None
    assert WarmJob.of(FakeTorrentEngine(torrent_files=[TorrFile(1, "")]), entry, "hash") is None
