"""Запускает упаковку медиапотока через переданный перекодировщик."""

from dataclasses import dataclass

from torrcast.domain.transcode_job import TranscodeJob
from torrcast.ports.transcoder import Transcoder


@dataclass(slots=True)
class Pack:
    """Передаёт неизменяемое задание внешнему упаковщику."""

    transcoder: Transcoder

    def run(self, job: TranscodeJob) -> None:
        self.transcoder.start(job)
