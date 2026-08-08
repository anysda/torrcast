"""Общее для тестов потока: self-signed серт, синтетический ролик-источник и заглушки
упаковки, которые нужны сразу двум наборам тестов.
"""

from __future__ import annotations

import socket
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from torrcast import cli, console
from torrcast.facts import Origin

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.stream import Packer

#: Длина синтетического ролика. Держим её кратной сетке HLS и с запасом в несколько
#: сегментов: на сетке 10 с двадцатисекундный ролик — это всего два сегмента,
#: и «продолжить с середины» на нём проверять уже нечего.
CLIP_SECONDS = 60


def free_port() -> int:
    """Свободный порт спрашивается у ядра, а не пишется константой в тесте.

    Раздача поднимается на настоящем сокете, поэтому прибитый номер делает тесты
    взаимно исключающими: два прогона рядом (соседний worktree, повторный запуск того
    же файла) дерутся за bind, и проигравший падает не по делу. ``bind`` на порт 0
    отдаёт номер, который в этот момент свободен, и он же сразу освобождается: сокет
    только привязан, соединений на нём не было, поэтому TIME_WAIT ему не грозит и
    сервер встаёт на то же место.

    Порт спрашивать надо перед самой раздачей, а не заранее и не на весь модуль: между
    ответом ядра и ``listen`` окно всё же есть, и чем оно короче, тем лучше.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(autouse=True)
def _silent_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Справка молчит, пока тест не попросит обратного.

    Тесты в сеть не ходят - ни за справкой, ни за чем-либо ещё. Заодно это и есть штатный
    случай «сети нет»: путь добора обязан работать и без справки.
    """
    monkeypatch.setattr(cli, "origin", lambda title, series=False: Origin())


@pytest.fixture(autouse=True)
def _pretend_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Под pytest терминала нет, а вопросы проверять надо.

    Без терминала ``ask_line`` штатно берёт дефолт и не спрашивает — это отдельное
    требование, и у него есть свои тесты. Всем остальным нужен обычный «человеческий» pty,
    поэтому по умолчанию притворяемся терминалом, а ``builtins.input`` тесты подменяют
    сами.
    """
    monkeypatch.setattr(console, "stdin_is_tty", lambda: True)


@pytest.fixture(scope="session")
def tls(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    """Self-signed для dev. В бою на это место встанут файлы LE — меняется только путь."""
    directory = tmp_path_factory.mktemp("tls")
    cert, key = directory / "torrcast.crt", directory / "torrcast.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
         "-keyout", str(key), "-out", str(cert), "-subj", "/CN=torrcast.example.com",
         "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "subjectAltName=DNS:torrcast.example.com,IP:127.0.0.1"],
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
def clip_hevc(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Ролик-источник в HEVC — то, чего приёмник не декодирует вовсе.

    Такой файл показ обязан перекодировать ЦЕЛИКОМ (:data:`torrcast.stream.RECODE_CODECS`),
    а не посегментно по весу: смешанный поток H.264 и HEVC живой Q70D не доигрывает.
    Кадр мелкий и ``ultrafast`` — ролик собирается за секунды.
    """
    path = tmp_path_factory.mktemp("src-hevc") / "clip.mkv"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(CLIP_SECONDS),
         "-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=none:keyint=50",
         "-c:a", "ac3", "-ac", "6", "-y", str(path)],
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
    развалила бы тест, а показ таких сигналов больше не шлёт.
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
    out: Path,
    first: int = 0,
    code: int | None = None,
    edge: int | None = None,
    run: Path | None = None,
    last: int = -1,
    at: float = 0.0,
    rate: float = 0.0,
    burst: float = 0.0,
    began: float = 0.0,
) -> Packer:
    """Прогон упаковки без ffmpeg: сегменты в ``out`` кладёт сам тест.

    Каталог прогона (``out/pack``) не создаётся: значит :meth:`Packer.publish` выкладывать
    нечего, и наружу остаётся ровно то, что тест положил своими руками.

    ``edge`` — честный край прогона (:attr:`torrcast.stream.Packer.edge`), то есть докуда
    **этот** прогон выложил. Без ffmpeg двигать его некому, поэтому фикстура спрашивает
    об этом тест. Умолчание — «выложил всё, что лежит в каталоге на момент создания»:
    так читается обычный случай «тест положил куски руками, они и есть работа прогона».
    Куски, положенные ПОСЛЕ создания, краем уже не считаются — ровно этим отличается
    честный край от глоба каталога, и на этом различии держится расчёт запаса показа.

    ``at``/``rate``/``burst``/``began`` — планка чтения ffmpeg (:meth:`Packer.eta`): с
    какой секунды фильма прогон читает вход, в каком темпе, сколько секунд читал на полной
    скорости и когда начался. Умолчание — темпа нет, то есть ждать упаковку не надо
    никогда: так читаются все тесты, где вопрос не про темп.

    ``run`` и ``last`` нужны там, где проверяется сама выкладка: каталог прогона со
    своими кусками и предел захода кодировщика (:attr:`torrcast.stream.Packer.last`).
    """
    from torrcast.stream import PACK_DIR, Packer, segment_slot

    if edge is None:
        made = [s for s in (segment_slot(p.name) for p in out.glob("v*.ts")) if s >= first]
        edge = max(made, default=first - 1)
    return Packer(
        proc=FakeProc(code),  # type: ignore[arg-type]
        out=out,
        run=out / PACK_DIR if run is None else run,
        first=first,
        edge=edge,
        last=last,
        at=at,
        rate=rate,
        burst=burst,
        began=began or time.monotonic(),
    )
