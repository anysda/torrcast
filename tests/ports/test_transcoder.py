"""Проверяет контракт перекодировщика и поведение его фейка."""

from tests.fakes.transcoder import FakeTranscoder
from torrcast.domain.transcode_job import TranscodeJob
from torrcast.ports.transcoder import Transcoder


def test_fake_records_job_and_stop() -> None:
    job = TranscodeJob("source", "/tmp/out", 4, 2)
    fake = FakeTranscoder()
    port: Transcoder = fake
    port.start(job)
    port.stop()
    assert (fake.jobs, fake.stop_count) == ([job], 1)
