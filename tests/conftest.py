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


def fake_packer(out: Path, first: int = 0, code: int | None = None) -> Packer:
    """Прогон упаковки без ffmpeg: сегменты в ``out`` кладёт сам тест.

    Каталог прогона (``out/pack``) не создаётся: значит :meth:`Packer.publish` выкладывать
    нечего, и наружу остаётся ровно то, что тест положил своими руками.
    """
    from torrcast.stream import PACK_DIR, Packer

    return Packer(proc=FakeProc(code), out=out, run=out / PACK_DIR, first=first)  # type: ignore[arg-type]
