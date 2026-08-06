"""Общее для тестов потока: self-signed серт, синтетический ролик-источник и заглушки
упаковки, которые нужны сразу двум наборам тестов.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from torrcast import console

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.stream import Packer

#: Длина синтетического ролика. Держим её кратной сетке HLS и с запасом в несколько
#: сегментов: на сетке 10 с (§6 SPEC-v2) двадцатисекундный ролик — это два сегмента,
#: и «продолжить с середины» на нём проверять уже нечего.
CLIP_SECONDS = 60


@pytest.fixture(autouse=True)
def _pretend_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Под pytest терминала нет, а вопросы проверять надо (§3 SPEC-v2).

    Без терминала ``ask_line`` штатно берёт дефолт и не спрашивает — это отдельное
    требование, и у него есть свои тесты. Всем остальным нужен «как у владельца» pty,
    поэтому по умолчанию притворяемся терминалом, а ``builtins.input`` тесты подменяют
    сами.
    """
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)


@pytest.fixture(scope="session")
def tls(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    """Self-signed для dev. На стенде на это место встанут файлы LE — меняется только путь."""
    directory = tmp_path_factory.mktemp("tls")
    cert, key = directory / "torrcast.crt", directory / "torrcast.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
         "-keyout", str(key), "-out", str(cert), "-subj", "/CN=torrcast.anysda.space",
         "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "subjectAltName=DNS:torrcast.anysda.space,IP:127.0.0.1"],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(cert), str(key)


@pytest.fixture(scope="session")
def clip(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Ролик-источник: H.264 + AC3 5.1 — ровно тот звук, который ресиверу отдавать нельзя."""
    path = tmp_path_factory.mktemp("src") / "clip.mkv"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(CLIP_SECONDS),
         "-c:v", "libx264", "-preset", "ultrafast", "-g", "50", "-c:a", "ac3", "-ac", "6",
         "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_mp4(clip: str, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Тот же ролик в mp4 с ``moov`` в голове — так его пишут релизы для сети (YTS).

    Пересобирается из mkv-ролика копией битстрима: карта опорных кадров обязана получиться
    той же самой, из какого бы контейнера её ни доставали, и тест это проверяет.
    ``-bf 2`` в исходном ролике нет, поэтому ``ctts`` в файле может и не быть — специально
    ради него ниже собирается :func:`clip_mp4_bframes`.
    """
    path = tmp_path_factory.mktemp("src-mp4") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-movflags", "+faststart", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_mp4_tail(clip: str, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Тот же ролик, но ``moov`` в хвосте: так пишет ffmpeg без ``faststart``.

    Такой файл встречается в раздачах, собранных «как получилось», и карта из него обязана
    сниматься тоже — не вычитывая при этом ``mdat`` целиком.
    """
    path = tmp_path_factory.mktemp("src-mp4-tail") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.fixture(scope="session")
def clip_mp4_bframes(tmp_path_factory: pytest.TempPathFactory) -> str:
    """mp4 с B-кадрами и списком правок: ``ctts`` и ``elst`` не пустые.

    Ровно на этой паре ломаются самодельные разборы: без ``ctts`` время опорного кадра
    получается временем ДЕКОДИРОВАНИЯ, а не тем, что показывает ffprobe и по чему режет
    сегментный муксер; без ``elst`` вся карта уезжает на пару кадров.
    """
    path = tmp_path_factory.mktemp("src-mp4-bf") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(CLIP_SECONDS),
         "-c:v", "libx264", "-preset", "ultrafast", "-g", "50", "-bf", "3",
         "-c:a", "aac", "-movflags", "+faststart", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


class FakeProc:
    """Процесс упаковки: умеет ровно то, что от него нужно показу.

    Сигналов остановки у него нет вовсе — попытка придержать упаковку SIGSTOP'ом
    развалила бы тест, а показ таких сигналов больше не шлёт (§6 SPEC-v2).
    """

    def __init__(self, code: int | None = None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.code = -15

    def wait(self, timeout: float | None = None) -> int:
        return -15


def fake_packer(
    out: Path, first: int = 0, code: int | None = None, edge: int | None = None
) -> Packer:
    """Прогон упаковки без ffmpeg: сегменты в ``out`` кладёт сам тест.

    Каталог прогона (``out/pack``) не создаётся: значит :meth:`Packer.publish` выкладывать
    нечего, и наружу остаётся ровно то, что тест положил своими руками.

    ``edge`` — честный край прогона (:attr:`torrcast.stream.Packer.edge`), то есть докуда
    **этот** прогон выложил. Без ffmpeg двигать его некому, поэтому фикстура спрашивает
    об этом тест. Умолчание — «выложил всё, что лежит в каталоге на момент создания»:
    так читается обычный случай «тест положил куски руками, они и есть работа прогона».
    Куски, положенные ПОСЛЕ создания, краем уже не считаются — ровно этим отличается
    честный край от глоба каталога, и на этом стоит §7.4 SPEC-v2.
    """
    from torrcast.stream import PACK_DIR, Packer, segment_slot

    if edge is None:
        made = [s for s in (segment_slot(p.name) for p in out.glob("v*.ts")) if s >= first]
        edge = max(made, default=first - 1)
    return Packer(proc=FakeProc(code), out=out, run=out / PACK_DIR, first=first, edge=edge)  # type: ignore[arg-type]
