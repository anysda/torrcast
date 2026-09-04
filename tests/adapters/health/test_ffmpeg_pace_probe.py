"""Проверяет реальный ffmpeg-темп: то же измерение, что и install.sh (TC-1048).

Проба идёт БОЕВОЙ проводкой - тем же классом, что заводит
:func:`torrcast.runtime.wire.wire` для ``cast doctor`` - без фабрикации аргументов:
реальный ffmpeg, реальный ``subprocess``, реальные секунды.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from torrcast.adapters.health.ffmpeg_pace_probe import FfmpegPaceProbe

#: TC-1048. Измерено вручную на реальных бинарях (см. отчёт): у 8.0.1 burst инертен
#: (7.7 с из 8 заказанных) и посадка на 10-й секунде ждёт больше 11 с; 6.1.1/7.1.4/7.1.5
#: держат обе пробы в 0.02-0.13 с. Таблица не гадает про версии, которых не измеряли.
_KNOWN_BAD = {"8.0.1"}
_KNOWN_GOOD = {"6.1.1", "7.1.4", "7.1.5"}

#: Соседняя песочница (только чтение, см. CLAUDE.md): бинари живут там, пока живёт она.
_NEIGHBOUR = Path("/tmp/tc160/bin")


def _real_ffmpeg_version(ff: str) -> str:
    """Голый номер, без ревизии дистрибутива: apt зовёт 8.0.1 «8.0.1-3ubuntu2»."""
    out = subprocess.run([ff, "-version"], capture_output=True, text=True, check=True).stdout
    return out.split()[2].split("-")[0]


def test_the_probe_returns_none_when_ffmpeg_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Программа не найдена вовсе - ролик собирать нечем, и проба отвечает ``None``."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert FfmpegPaceProbe.ffmpeg_pace() is None


@pytest.mark.ffmpeg
def test_the_probe_judges_the_real_system_ffmpeg_if_its_version_was_measured() -> None:
    """🔴 Отрицательная проба TC-1048: обязана падать по assert, а не по AttributeError -
    класс и метод реальные, приговор читается из настоящих измеренных секунд.
    """
    ff = shutil.which("ffmpeg")
    if ff is None:
        pytest.skip("ffmpeg отсутствует на PATH")
    version = _real_ffmpeg_version(ff)
    if version not in _KNOWN_BAD | _KNOWN_GOOD:
        pytest.skip(f"ffmpeg {version} не входит в измеренный список - таблица не гадает")
    pace = FfmpegPaceProbe.ffmpeg_pace()
    assert pace is not None, "ffmpeg на PATH не собрал синтетический ролик"
    honest = pace.burst_honored and pace.entry_paced
    numbers = (
        f"baseline={pace.baseline_seconds}s burst={pace.burst_seconds}s entry={pace.entry_seconds}s"
    )
    if version in _KNOWN_BAD:
        assert not honest, f"ffmpeg {version} обязан быть отвергнут: {numbers}"
    else:
        assert honest, f"ffmpeg {version} обязан быть принят: {numbers}"


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    "binary,ld_dir",
    [("ffmpeg-611", "lib611"), ("ffmpeg-715", "lib715")],
)
def test_the_probe_accepts_neighbouring_known_good_builds(
    binary: str, ld_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Опортунистическая проверка на бинарях соседней песочницы (только чтение)."""
    ff = _NEIGHBOUR / binary
    if not ff.exists():
        pytest.skip("контрольные бинари /tmp/tc160 недоступны в этом окружении")
    monkeypatch.setattr("shutil.which", lambda name: str(ff))
    monkeypatch.setenv("LD_LIBRARY_PATH", f"/tmp/tc160/{ld_dir}")
    pace = FfmpegPaceProbe.ffmpeg_pace()
    assert pace is not None
    assert pace.burst_honored and pace.entry_paced, pace
