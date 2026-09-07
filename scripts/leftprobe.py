#!/usr/bin/env python3
"""Замер срока «ухожу» (TC-1124): от настоящего ``F5`` до первого свежего доклада.

Инструмент разработчика: headless Chromium (playwright), в устанавливаемый пакет не
входит - как ``scripts/decodebench.py`` и ``scripts/web-acceptance.py``. Зовётся против
живого запущенного экземпляра torrcast, у которого уже идёт показ на вкладке::

    PLAYWRIGHT_BROWSERS_PATH=... python3 \
        scripts/leftprobe.py --base http://ХОСТ:ПОРТ

Мера прибора - не показ и не упаковка, а сама вкладка: сколько живых секунд проходит
между ``pagehide`` (обновление страницы посылает его тем же путём, что и закрытие) и
первым ``POST /api/web/position`` со свежим докладом ПОСЛЕ перезагрузки. Это ровно та
пара событий, которую разводит :attr:`torrcast.domain.receiver_profile.
ReceiverProfile.left_after`: короче него - обновление НЕ роняет показ, длиннее -
уже настоящий уход. Продукт при этом не трогается вовсе: прибор смотрит только на
сетевые заходы браузера через ``page.on('request', ...)``, тело докладов не разбирает
и решение продукта не подменяет.
"""

from __future__ import annotations

import argparse
import time
from typing import Any


def _wait_playback(page: Any, timeout_ms: int = 90000) -> None:
    page.wait_for_selector("video", timeout=timeout_ms)
    page.wait_for_function(
        "() => { const v = document.querySelector('video'); return !!v && v.readyState >= 3; }",
        timeout=timeout_ms,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8479")
    parser.add_argument("--rounds", type=int, default=3, help="сколько раз обновить страницу")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(args.base + "/play", wait_until="load", timeout=15000)
        _wait_playback(page)

        gaps: list[float] = []
        for i in range(args.rounds):
            marks: dict[str, float] = {}

            # ``navigator.sendBeacon`` шлёт ``phase: "left"`` Blob-телом, а Playwright
            # ``request.post_data()`` для такого запроса надёжно отдаёт ``None`` -
            # разбирать тело смысла нет. Зато момент отправки известен и без разбора:
            # ``pagehide`` уходит СИНХРОННО с началом самой перезагрузки (спека), так что
            # веха «ухожу» - это сам вызов ``page.reload()``, а не какой-то из докладов.
            def _on_request(request: Any, marks: dict[str, float] = marks) -> None:
                if request.method != "POST" or "/api/web/position" not in request.url:
                    return
                if "resumed" not in marks:
                    marks["resumed"] = time.monotonic()

            page.on("request", _on_request)
            marks["left"] = time.monotonic()
            page.reload(wait_until="load", timeout=15000)
            _wait_playback(page)
            deadline = time.monotonic() + 10.0
            while "resumed" not in marks and time.monotonic() < deadline:
                page.wait_for_timeout(200)
            page.remove_listener("request", _on_request)
            if "resumed" in marks:
                gap = marks["resumed"] - marks["left"]
                gaps.append(gap)
                print(f"обновление {i + 1}: pagehide -> свежий доклад за {gap:.2f} с")
            else:
                print(f"обновление {i + 1}: свежего доклада после перезагрузки не поймано")

        browser.close()

    if gaps:
        print(f"худший разрыв {max(gaps):.2f} с, лучший {min(gaps):.2f} с, раундов {len(gaps)}")
    return 0 if gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())
