"""Настоящий темп ffmpeg: то же измерение, что и в install.sh (TC-1048), портом.

Что СЧИТАЕТСЯ здоровым решает домен (:mod:`torrcast.domain.ffmpeg_pace`); тут - только
КАК узнать: собрать синтетический ролик и засечь секунды на трёх живых прогонах.
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from torrcast.domain.ffmpeg_pace import (
    PACE_BURST_SECONDS,
    PACE_DEADLINE_SECONDS,
    PACE_ENTRY_READ_SECONDS,
    PACE_ENTRY_SECONDS,
    FfmpegPace,
)


class FfmpegPaceProbe:
    """Секунды трёх прогонов; своей клетки не держит - каждый вызов чист заново."""

    @staticmethod
    def ffmpeg_pace() -> FfmpegPace | None:
        """``None`` - ffmpeg не запускается вовсе или синтетический ролик не собрался."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            return None
        with tempfile.TemporaryDirectory() as work:
            clip = Path(work) / "pace.ts"
            total = int(PACE_ENTRY_SECONDS + PACE_ENTRY_READ_SECONDS + 4)
            built = subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:duration={total}",
                    "-f", "lavfi", "-i", f"sine=duration={total}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                    "-g", "25", "-keyint_min", "25", "-c:a", "aac", "-f", "mpegts", str(clip),
                ],
                capture_output=True,
                timeout=PACE_DEADLINE_SECONDS * 4,
                check=False,
            )  # fmt: skip
            if built.returncode != 0 or not clip.exists():
                return None
            baseline = _timed(
                ffmpeg,
                ["-readrate", "0", "-copyts", "-i", str(clip),
                 "-t", str(PACE_BURST_SECONDS), "-c", "copy", "-f", "null", "-"],
            )  # fmt: skip
            burst = _timed(
                ffmpeg,
                ["-readrate", "1", "-readrate_initial_burst", str(PACE_BURST_SECONDS),
                 "-copyts", "-i", str(clip),
                 "-t", str(PACE_BURST_SECONDS), "-c", "copy", "-f", "null", "-"],
            )  # fmt: skip
            entry = _timed(
                ffmpeg,
                ["-readrate", "1", "-copyts", "-ss", str(PACE_ENTRY_SECONDS), "-i", str(clip),
                 "-t", str(PACE_ENTRY_READ_SECONDS), "-c", "copy", "-f", "null", "-"],
            )  # fmt: skip
        return FfmpegPace(baseline_seconds=baseline, burst_seconds=burst, entry_seconds=entry)


def _timed(ffmpeg: str, args: list[str]) -> float:
    """Секунды до завершения процесса; не дождались - потолок сам и есть ответ."""
    start = time.monotonic()
    try:
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],
            capture_output=True,
            timeout=PACE_DEADLINE_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PACE_DEADLINE_SECONDS
    return time.monotonic() - start
