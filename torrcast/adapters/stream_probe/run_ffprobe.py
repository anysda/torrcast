"""Запуск ffprobe со срывом ожидания, когда рой замолчал.

Зовёт его щуп паспорта (:func:`probe`), и только он."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

from torrcast.domain.swarm_error import SwarmError


def _run_ffprobe(command: list[str], timeout: float, alive: Callable[[], bool] | None) -> str:
    """Запустить ffprobe и вернуть stdout. Без ``alive`` — прежний :func:`subprocess.run`
    с тем же таймаутом; с ``alive`` — то же самое, но с возможностью оборвать чтение
    раньше бюджета, когда рой замолчал (:func:`swarm_pulse`).

    Живой релиз проходит ровно как раньше: ffprobe дочитывает заголовок и выходит сам,
    ``alive`` всё это время True, никакой лишней секунды не добавляется. Обрыв случается
    только на молчащем рое — там, где иначе сгорел бы весь ``timeout``.
    """
    if alive is None:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
        return done.stdout
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            out, err = proc.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            if not alive():
                proc.kill()
                proc.communicate()
                raise SwarmError("рой молчит - за отсрочку не пришло ни байта потока") from None
            if time.monotonic() >= deadline:
                proc.kill()
                proc.communicate()
                raise subprocess.TimeoutExpired(command, timeout) from None
            continue
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, command, out, err)
        return out
