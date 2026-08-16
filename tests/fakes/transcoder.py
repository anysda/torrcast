"""Изображает для тестов перекодировщик и записывает задания."""

from dataclasses import dataclass, field

from torrcast.domain.transcode_job import TranscodeJob


@dataclass
class FakeTranscoder:
    jobs: list[TranscodeJob] = field(default_factory=list)
    stop_count: int = 0

    def start(self, job: TranscodeJob) -> None:
        self.jobs.append(job)

    def stop(self) -> None:
        self.stop_count += 1
