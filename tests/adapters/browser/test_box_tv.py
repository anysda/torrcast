"""Проверяет слово ящика о приёмнике живого показа: телевизор или вкладка."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser.box_tv import box_tv
from torrcast.adapters.browser.write_web_box import write_web_box


def test_a_show_raised_by_the_tab_is_not_the_tv(tmp_path: Path) -> None:
    """Вкладка пишет свой ящик без ``tv``: её показ назван браузером, не телевизором."""
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Кино", at=0.0, key="k1")

    assert box_tv(tmp_path) is False


def test_a_show_raised_on_the_tv_is_the_tv(tmp_path: Path) -> None:
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Кино", at=0.0, key="k1", tv=True)

    assert box_tv(tmp_path) is True


def test_an_empty_box_keeps_the_old_word(tmp_path: Path) -> None:
    """Ящика нет - выдумывать нечего: строка остаётся прежней, про телевизор."""
    assert box_tv(tmp_path) is True


def test_a_named_tv_holds_a_tab_show_carried_to_it(tmp_path: Path) -> None:
    """Ящик вкладки без ``tv``, но телевизор у машины назван: «На ТВ» ящик не переписывает."""
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Кино", at=0.0, key="k1")

    assert box_tv(tmp_path, "Living Room") is True
    assert box_tv(tmp_path, "browser") is False
