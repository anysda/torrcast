"""Получает паспорт потока через ffprobe; его подключает среда исполнения."""

from dataclasses import dataclass

from torrcast.adapters.ffprobe.parse_media import parse_media
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.ports.process_runner import ProcessRunner


@dataclass(frozen=True, slots=True)
class FfprobeProber:
    """Реализует порт щупа поверх переданного запуска внешних процессов."""

    runner: ProcessRunner
    timeout: float = 90.0

    def probe(self, source_url: str) -> Media:
        entries = (
            "format=duration:"
            "stream=index,codec_name,codec_type,channels,width,height,bit_rate,profile,pix_fmt,"
            "color_transfer,field_order:stream_tags"
        )
        command = ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", source_url]
        result = self.runner.run(command, timeout=self.timeout)
        if result.returncode:
            raise InfraError(f"ffprobe не прочитал поток: {result.stderr.strip()[:120]}")
        return parse_media(result.stdout)
