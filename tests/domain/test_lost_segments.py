"""Зеркало :mod:`torrcast.domain.lost_segments`."""

from __future__ import annotations

from torrcast.domain.lost_segments import lost_segments


def test_every_word_of_the_decoder_about_a_missing_piece_is_a_gap() -> None:
    """Кусок, до декодера не доехавший, для приёмки и есть разрыв - как бы он ни назвался."""
    journal = "\n".join(
        [
            "[hls @ 0x1] Failed to open segment 12 of playlist 0",
            "[hls @ 0x1] Error opening input: Server returned 404 Not Found",
            "[hls @ 0x1] Cannot reload playlist",
            "[hls @ 0x1] skipping 1 segment ahead, expired from playlists",
        ]
    )

    assert lost_segments(journal) == 4


def test_a_clean_journal_holds_no_gaps() -> None:
    """Обычная работа декодера разрывом не считается."""
    assert lost_segments("") == 0
    assert lost_segments("frame= 250 fps= 25 q=-1.0 size=N/A time=00:00:10.00 speed=12x") == 0


def test_the_case_of_the_message_does_not_hide_a_gap() -> None:
    """Регистр в журнале ffmpeg плавает, а разрыв от этого разрывом быть не перестаёт."""
    assert lost_segments("FAILED TO OPEN SEGMENT 3") == 1
