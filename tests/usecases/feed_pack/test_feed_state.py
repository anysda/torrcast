"""Поля ленты показа: пороги приёмника по умолчанию и голос показа наружу."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import feed, grid
from torrcast.domain.hls_settings import PACK_PENDING_BYTES
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.feed_pack.feed_state import _State

if TYPE_CHECKING:
    from pathlib import Path


def test_the_defaults_of_the_receiver_come_from_its_cautious_profile(tmp_path: Path) -> None:
    """Запас, ожидание и потолок куска - свойства приёмника, а не медиатракта."""
    show = _State(source="src", audio=0, out=tmp_path, grid=grid())

    assert show.burst == CAUTIOUS.burst
    assert show.wait == CAUTIOUS.hold_seconds
    assert show.cap == CAUTIOUS.max_segment_bytes
    assert show.pending_cap == PACK_PENDING_BYTES
    assert show.jump == CAUTIOUS.jump
    assert show.seam_lead == CAUTIOUS.seam_lead


def test_the_thresholds_of_the_show_are_the_measured_ones(tmp_path: Path) -> None:
    """Семь сегментов вперёд, пятнадцать секунд ожидания, две минуты назад, три обрыва.

    Каждое число - замер живого показа, а не круглая цифра: семь сегментов - это то,
    что Q70D просит разом после перемотки, пятнадцать секунд - вчетверо дороже
    перезапуска и вчетверо дешевле замеренного ожидания.
    """
    show = _State(source="src", audio=0, out=tmp_path, grid=grid())

    assert show.ahead == 7
    assert show.jump == 15.0
    assert show.keep == 120.0
    assert show.limit == 3
    assert show.readrate == 1.0


def test_a_fresh_show_has_no_run_no_crashes_and_nothing_skipped(tmp_path: Path) -> None:
    """Свежая лента ничего не паковала, ни разу не оборвалась и ничего не пропускала."""
    show = _State(source="src", audio=0, out=tmp_path, grid=grid())

    assert show.packer is None and show.crashes == 0 and show.restarted == 0.0
    assert show.fatal == "" and show.offline == "" and show.skipped == set()
    assert show.vault is None and show.recoder is None and show.encode is None


def test_two_shows_never_share_one_set_of_skipped_places(tmp_path: Path) -> None:
    """Пропущенные места - у каждого показа свои: общий набор пропустил бы чужое кино."""
    first = feed(tmp_path / "a")
    second = feed(tmp_path / "b")

    first.skipped.add(5)

    assert second.skipped == set() and first.lock is not second.lock


def test_the_show_speaks_only_when_there_is_someone_to_listen(tmp_path: Path) -> None:
    """Голос показа уходит в журнал зрителя; журнала нет - строка не выдумывается."""
    said: list[str] = []
    talkative = feed(tmp_path / "a", log=said.append)
    talkative._say("упаковка с 0.0 с")

    assert said == ["упаковка с 0.0 с"]

    feed(tmp_path / "b")._say("в никуда")  # молчащий показ не имеет права падать
