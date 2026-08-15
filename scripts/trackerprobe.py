#!/usr/bin/env python3
"""Проверить UDP-connect публичных трекеров с конкретной машины."""

from __future__ import annotations

import argparse
import json
import random
import socket
import struct
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrcast.search import PUBLIC_TRACKERS


def connect(address: str, timeout: float = 4.0) -> dict[str, Any]:
    where = address.removeprefix("udp://").split("/", 1)[0]
    host, _colon, port = where.rpartition(":")
    number = int(port) if port.isdigit() else 0
    transaction = random.randrange(2**32)
    packet = struct.pack("!QII", 0x41727101980, 0, transaction)
    began = time.monotonic()
    # Мёртвый трекер сужает список ответивших, а не роняет весь щуп, поэтому под охраной
    # тут ВЕСЬ поход, а не одна отправка. Резолв стоит внутри: ``socket.gaierror`` у
    # исчезнувшего имени - это такой же отказ источника, как и молчание. И ``struct.error``
    # назван прямо: короткий или мусорный ответ короче восьми байт роняет ``unpack``, а он
    # НЕ ``OSError``, и такой трекер уносил с собой опрос всех остальных.
    try:
        ip = socket.gethostbyname(host)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (ip, number))
            answer, _peer = sock.recvfrom(2048)
        action, echoed = struct.unpack("!II", answer[:8])
        ok = action == 0 and echoed == transaction
    except (OSError, struct.error, ValueError):
        ok = False
    return {
        "tracker": host,
        "port": number,
        "ok": ok,
        "seconds": round(time.monotonic() - began, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args(argv)
    rows = [connect(address, args.timeout) for address in PUBLIC_TRACKERS]
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    print(
        json.dumps(
            {"answered": sum(bool(row["ok"]) for row in rows), "total": len(rows)}, sort_keys=True
        )
    )
    return 0 if any(row["ok"] for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
