"""Проверяет сборку команды упаковки без запуска ffmpeg."""

from dataclasses import dataclass

from torrcast.adapters.ffmpeg.pack_command import pack_command


@dataclass
class _Grid:
    bounds: tuple[float, ...] = (0.0, 10.0, 20.0)
    count: int = 3
    origin: float = 1.4
    on_keys: bool = True

    def start(self, slot: int) -> float:
        return self.bounds[slot]

    def end(self, slot: int) -> float:
        return self.bounds[slot + 1] if slot + 1 < self.count else 30.0


def test_builds_segment_command_from_supplied_grid() -> None:
    command = pack_command("http://source", 2, "/run/", _Grid(), 1, 9.5, burst=30.0)
    assert command[:3] == ["ffmpeg", "-hide_banner", "-loglevel"]
    assert command[command.index("-map") + 1] == "0:v:0"
    assert "0:a:2" in command
    assert command[-1] == "/run/v%d.ts"
    assert "-output_ts_offset" in command
    assert any("10.500" in argument for argument in command)
