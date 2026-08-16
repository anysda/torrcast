"""Запускает и останавливает перекодирование по запросу сценариев."""

from typing import Protocol

from torrcast.domain.transcode_job import TranscodeJob


class Transcoder(Protocol):
    def start(self, job: TranscodeJob) -> None: ...
    def stop(self) -> None: ...
