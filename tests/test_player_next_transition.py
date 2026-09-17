"""Сторож перехода между сериями (TC-1336): плашка честная, кадр без чёрного экрана.

Требование: за ``TCPlayerNext.SECONDS`` до конца - плашка «Смотреть»/«Отмена»; счёт либо
честно доходит до нуля, либо снимается кнопкой - обрыва на середине счёта не бывает
(живой замер до и после правки - в ``results-a.md`` полосы A).
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"


def _block(text: str, header: str, next_marker: str = "\n  },") -> str:
    found = text.split(header, 1)
    assert len(found) == 2, f"в файле нет {header!r}"
    return found[1].split(next_marker, 1)[0]


def test_the_countdown_trigger_uses_the_promised_seconds_not_a_hardcoded_one() -> None:
    """Плашка обещает ``TCPlayerNext.SECONDS`` - триггер обязан читать то же число.

    Прежний порог (``<= 1``) звал плашку за 1 с до конца, а она сама считала 10 - врала
    «10» при 0.74 с реального остатка (замер CT510+CT511 17-09-2026).
    """
    body = _block((STATIC / "player.js").read_text("utf-8"), "_onTimeUpdate() {")
    assert "TCPlayerNext.SECONDS" in body, "триггер не смотрит на срок плашки"
    assert not re.search(r"<=\s*1\)", body), "порог всё ещё зашитая 1 секунда"


def test_the_countdown_card_is_removed_on_natural_expiry_too() -> None:
    """Досчитала сама - карточка уходит тем же путём, что и по кнопке (``stop()``).

    Раньше ветка истечения звала только ``clearInterval``, минуя ``card.remove()`` -
    карточка висела на «0» до следующей перерисовки.
    """
    text = (STATIC / "player-next.js").read_text("utf-8")
    timer_body = _block(text, "setInterval(() => {", "\n    }, 1000);")
    expiry = _block(timer_body, "if (left <= 0) {", "\n      }")
    assert "stop();" in expiry, "истечение счёта не убирает карточку через stop()"


def test_rebox_defers_to_a_pending_box_while_the_countdown_is_up() -> None:
    """Пока плеер досчитывает плашку (``player._advanced``), ``rebox()`` не трогает оверлей.

    Прежде ``rebox()`` звала ``_screenBuffering()``/``_attach()`` сразу по новому ключу -
    ``overlay.replaceChildren()`` внутри стирала карточку отсчёта на середине счёта.
    """
    text = (STATIC / "player-box.js").read_text("utf-8")
    rebox = _block(text, "async rebox(player) {")
    assert "player._advanced" in rebox, "rebox() больше не смотрит на отсчёт плеера"
    assert "player._pendingBox = box;" in rebox, "новый ящик негде придержать на время счёта"
    assert "_screenBuffering()" not in rebox, "rebox() всё ещё меняет кадр немедленно"
    assert "_attach(" not in rebox, "rebox() всё ещё меняет кадр немедленно"
    assert "TCPlayerBox.apply(player, box);" in rebox, "готовый ящик не открывается через apply()"

    apply_body = _block(text, "apply(player, box) {")
    assert "_screenBuffering()" in apply_body
    assert "_attach(" in apply_body


def test_playing_next_opens_a_pending_box_without_a_second_round_trip() -> None:
    """``_playNext`` (истечение счёта/«Смотреть») открывает уже найденный ящик сама.

    Не через ``TCApi.box()`` заново - тот самый, что ``rebox()`` придержала в
    ``_pendingBox`` пока шёл счёт: это и убирает чёрный экран между сериями.
    """
    body = _block((STATIC / "player.js").read_text("utf-8"), "_playNext(ended) {")
    assert "TCPlayer._pendingBox" in body
    assert "TCPlayerBox.apply(TCPlayer, box)" in body
    assert "TCApi.next(ended)" in body
