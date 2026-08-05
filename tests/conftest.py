"""Общее для тестов потока: self-signed серт и синтетический ролик-источник."""

from __future__ import annotations

import subprocess

import pytest

from torrcast import console

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
