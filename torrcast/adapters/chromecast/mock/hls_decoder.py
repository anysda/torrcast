"""Декодер сухого приёмника: ffmpeg играет поток в ``/dev/null`` и отдаёт позицию."""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
import threading
from typing import IO, Any, Final

from torrcast.adapters.stream_pack import parse_manifest
from torrcast.domain.infra_error import InfraError
from torrcast.domain.lost_segments import lost_segments
from torrcast.domain.position import Position
from torrcast.domain.reception_report import ReceptionReport
from torrcast.domain.trimmed_playlist import trimmed_playlist

#: Что разрешено декодеру, когда плейлист подан ему файлом: сам файл и сеть, в которой
#: лежат сегменты. Без списка ffmpeg отказывается ходить с диска наружу («Protocol 'http'
#: not on whitelist») и не открывает вход вовсе.
PROTOCOLS: Final = "file,http,https,tcp,tls,crypto,data"


class HlsDecoder:
    """ffmpeg на месте декодера приёмника: тянет тот же поток, что и ТВ.

    Позиция берётся из ``-progress`` - ровно то, что ТВ отдал бы сторожу, - а разрывы
    считаются по журналу декодера. Оба живут один заход: показ либо снимают, либо грузят
    заново.
    """

    def __init__(
        self,
        report: ReceptionReport,
        ca: str = "",
        spawn: Any = subprocess.Popen,
        thread: Any = threading.Thread,
    ) -> None:
        self.report = report
        self.ca = ca
        #: Чем поднимаются декодер и его читатель. Умолчание боевое - настоящий ffmpeg и
        #: настоящий поток; тесту, который проверяет учёт позиции, сюда дают заглушки.
        self.spawn, self.thread = spawn, thread
        self.proc: subprocess.Popen[str] | None = None
        self.err: IO[bytes] | None = None
        self.pos = Position(0.0, 0.0, False)
        #: Вход закрыт: читатель дошёл до конца, либо показ сняли.
        self.done = threading.Event()
        #: С какой секунды фильма открыт этот заход: декодер считает время от себя.
        self.start = 0.0
        #: Срезанный плейлист этого захода; пусто - декодер открыт по адресу раздачи.
        self.playlist = ""
        self.follower: Any = None

    @property
    def finished(self) -> bool:
        """Декодер вышел нулём: вход кончился сам."""
        return self.proc is not None and self.proc.poll() == 0

    def open(self, url: str, body: str, at: float = 0.0) -> None:
        """Открыть поток с секунды ``at``: прошлый декодер снимается, новый заводится."""
        self.stop()
        self.done = threading.Event()  # прошлый читатель остановлен, у этого захода свой
        self.err = tempfile.TemporaryFile()  # noqa: SIM115 - живёт всё воспроизведение
        self.start = at
        source, offset = self.source(url, body, at)
        head: list[str] = []
        if source != url:
            head = ["-protocol_whitelist", PROTOCOLS]
        elif url.startswith("https://"):
            # ⚠️ Опции TLS ставятся только под https-адрес: на http ffmpeg не «игнорирует
            # лишнее», а падает с «Option tls_verify not found» ещё до открытия входа -
            # то есть на дефолтном транспорте не декодировал бы ничего.
            head = ["-tls_verify", "1", *(["-ca_file", self.ca] if self.ca else [])]
        command = [
            "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning", *head,
            *(["-ss", f"{offset:.3f}"] if offset > 0 else []),
            "-i", source, "-progress", "pipe:1", "-f", "null", "-",
        ]  # fmt: skip
        try:
            self.proc = self.spawn(command, stdout=subprocess.PIPE, stderr=self.err, text=True)
        except FileNotFoundError as exc:
            self.close_log()
            raise InfraError("ffmpeg не установлен") from exc
        # 🔴 Место захода, а не ноль: до первого слова декодера приёмник стоит ТАМ, куда
        # его послали, и живой приёмник отвечает ровно так - указатель держится на месте
        # захода, пока он копит фильм. С нулём продолжение с 0:20:00 читалось бы как
        # 0:00:00, и закладку сухим прогоном проверить было бы нельзя вовсе.
        self.pos = Position(at, 0.0, True)
        self.follower = self.thread(target=self.follow, daemon=True)
        self.follower.start()

    def source(self, url: str, body: str, at: float) -> tuple[str, float]:
        """Чем кормить декодер, чтобы он начал ровно там, откуда начинает приёмник.

        Плейлист со срезанной головой (:func:`torrcast.domain.trimmed_playlist`) кладётся
        файлом и живёт ровно один заход. Резать нечего - вход остаётся прежним: заход в
        первый же кусок и так начинается с головы, а растущий манифест (без ``ENDLIST``)
        обрезать нельзя - там ещё не известно, что будет дальше.

        ⚠️ Опции TLS с таким входом ffmpeg не принимает вовсе, и терять с ними нечего: в
        запросы сегментов он их не передаёт ни на каком входе. Единственную настоящую
        проверку серта раздачи делает не декодер, а :class:`HlsFetch`.
        """
        if at <= 0:
            return url, at
        segments, ended = parse_manifest(body)
        if not ended or not segments:
            return url, at
        cut = trimmed_playlist(segments, url.rsplit("/", 1)[0], at)
        if cut is None:
            return url, at
        text, offset = cut
        self.drop_list()  # плейлист живёт один заход, и прошлый уходит вместе с ним
        handle, self.playlist = tempfile.mkstemp(suffix=".m3u8")
        with os.fdopen(handle, "w", encoding="utf-8") as playlist:
            playlist.write(text)
        return self.playlist, offset

    def stop(self) -> None:
        """Остановить декодер и его читателя: показ снимают либо грузят заново."""
        self.done.set()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=5)
        # Журнал ffmpeg дочитывает :meth:`follow` - он же его и закроет; ждём его, чтобы
        # не отнять счёт разрывов, и закрываем сами, если он не дошёл или не заводился.
        if self.follower is not None:
            self.follower.join(timeout=5)
        self.follower = None
        self.close_log()
        self.pos = Position(self.pos.pos, self.pos.dur, False)

    def follow(self) -> None:
        """Позиция из ``-progress`` декодера и разрывы из его журнала."""
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            if line.startswith("out_time_us="):
                with contextlib.suppress(ValueError):
                    # Позиция абсолютная, как у живого приёмника: показ мог начаться с
                    # середины фильма, а декодер считает время от своего старта.
                    self.pos = Position(self.start + int(line[12:]) / 1e6, self.pos.dur, True)
        proc.wait()
        self.done.set()
        self.report.decoded = self.pos.pos
        err, self.err = self.err, None
        if err is not None:
            with err:
                err.seek(0)
                text = err.read().decode("utf-8", "replace")
            self.report.gaps += lost_segments(text)
        self.pos = Position(self.pos.pos, self.pos.dur, False)

    def close_log(self) -> None:
        """Закрыть журнал ffmpeg и убрать срезанный плейлист - оба живут один заход."""
        err, self.err = self.err, None
        if err is not None:
            err.close()
        self.drop_list()

    def drop_list(self) -> None:
        """Убрать срезанный плейлист прошлого захода; путь забирается себе."""
        cut, self.playlist = self.playlist, ""
        if cut:
            with contextlib.suppress(OSError):
                os.unlink(cut)
