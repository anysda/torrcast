"""Сторож на платформу игры: она сильнее вето видео-приметы (:data:`_PLATFORM_RE`).

Вето видео-приметы несёт всё правило N1-N4 и снимать его нельзя (сторож рядом -
:mod:`tests.domain.test_nonvideo_release_veto`). Но у названной платформы оно отнимало
единственное, чем игра о себе говорит: «... [Видеоролики в разрешении 4K] (2023) PC |
RePack-FitGirl» приезжал на полку «Новинки» плиткой фильма 2023 года в 2160p, потому что
`4K` в скобках перевешивало и `PC |`, и `RePack` разом (замер 07-09-2026 на живой ленте
стенда). Кто вернёт вето над платформой - здесь обязан покраснеть.
"""

from torrcast.domain.nonvideo_release import _is_nonvideo_release


def test_a_game_that_advertises_its_4k_cutscenes_is_still_a_game() -> None:
    assert _is_nonvideo_release(
        "Mortal Kombat 1 - Khaos Reigns Kollection "
        "[Видеоролики в разрешении 4K] (2023) PC | RePack-FitGirl"
    )


def test_a_platform_tail_outweighs_a_video_word_too() -> None:
    assert _is_nonvideo_release("Cyberpunk 2077 [v 2.1] (2020) 1080p PC")
    assert _is_nonvideo_release("[PS2] Ratchet: Deadlocked (2005) DVD5")


def test_a_repack_of_a_real_film_stays_a_film() -> None:
    """🔴 `repack` осталась СЛАБОЙ приметой нарочно: так метят и перевыпуск фильма.

    Сделать сильной её значило бы выкинуть настоящее кино целой сцен-меткой - ровно то,
    от чего вето и поставлено. Платформа же в имени фильма не пишется никогда.
    """
    assert not _is_nonvideo_release("Movie.2020.1080p.BluRay.REPACK.x264")


def test_a_film_without_any_platform_word_is_untouched() -> None:
    assert not _is_nonvideo_release("Дюна: Часть вторая (2024) BDRemux 2160p")
