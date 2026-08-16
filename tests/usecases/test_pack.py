"""Проверяет сценарий упаковки на фейковом перекодировщике."""

from tests.fakes.transcoder import FakeTranscoder
from torrcast.domain.transcode_job import TranscodeJob
from torrcast.usecases.pack import Pack


def test_pack_passes_job_to_transcoder() -> None:
    transcoder = FakeTranscoder()
    job = TranscodeJob("http://source", "/tmp/out", 42.0, 2)

    Pack(transcoder).run(job)

    assert transcoder.jobs == [job]
