"""Зеркало :mod:`torrcast.domain.entry`: запись состояния показа как чистое значение.

Переходы записи и закладку сторожит набор состояния (``tests/test_state.py``). Здесь -
то, что живёт только в самой записи: две доли, отвечающие на РАЗНЫЕ вопросы; поля, которые
относятся к файлу и обязаны обнуляться вместе со сменой файла; и признак сериала, который
нельзя выдавать по одной осечке разбора.
"""

from __future__ import annotations

from torrcast.domain.entry import ENDING_RATIO, WATCHED_RATIO, Entry

WHOLE = 1000.0


def movie(**fields: object) -> Entry:
    """Запись фильма: минимум обязательного, остальное по умолчанию."""
    return Entry(title="Картина", magnet="m", **fields)  # type: ignore[arg-type]


def pack(**fields: object) -> Entry:
    """Сериал с уже выбранной раздачей: три серии, у каждой свой файл."""
    return Entry(
        title="Сериал",
        magnet="m",
        kind="tv",
        season=1,
        episode=2,
        episodes=[[1, 2, 5], [1, 3, 6], [1, 4, 7]],
        **fields,  # type: ignore[arg-type]
    )


def test_the_credits_mark_is_never_stricter_than_the_watched_mark() -> None:
    """Две доли отвечают на разные вопросы, и та, что про титры, обязана быть не строже.

    «Досмотрено» решает, предлагать ли продолжение; «это был конец, а не обрыв» решает,
    воскрешать ли погасший экран. Сузь вторую относительно первой - и показ полез бы
    поднимать доигранное: экран гаснет на титрах штатно, а запись бы этого ещё не признала.
    """
    assert ENDING_RATIO <= WATCHED_RATIO
    assert 0.0 < ENDING_RATIO < 1.0, "доля титров обязана оставаться долей, а не концом ленты"


def test_an_unknown_length_never_gives_the_right_to_guess_the_share() -> None:
    """Без длительности доли считать не от чего, и обе мерки молчат.

    Приёмник знает длину не всегда. Начни запись угадывать - недосмотренный фильм с
    неизвестной длиной уходил бы в «досмотрено», и продолжить его стало бы нечем.
    """
    assert not movie(pos=WHOLE, dur=0.0).ending
    assert not movie(pos=WHOLE, dur=0.0).watched


def test_moving_to_another_file_drops_everything_that_belonged_to_the_old_one() -> None:
    """Прогрев и отметка темноты относятся к ФАЙЛУ, а файл после перехода другой.

    Оставь их - и ``cast status`` показывал бы на новой серии прогрев прошлой (враньё
    наружу), а показ считал бы новую серию погасшей ещё до того, как она началась.
    """
    watched = pack(pos=999.0, dur=WHOLE, warm=640.0, dark=1_700_000_000.0, dark_why="сеть")

    following = watched.advance()

    assert following.label == "s1e3", "перешли на следующую серию раздачи"
    assert following.warm == 0.0
    assert following.dark == 0.0
    assert following.dark_why == ""


def test_a_jump_inside_the_same_release_clears_the_same_fields() -> None:
    """Прыжок на другую серию - та же смена файла, и хвосты прошлого файла с ним не едут."""
    jumped = pack(warm=640.0, dark=1_700_000_000.0, dark_why="сеть").jump(1, 4)

    assert jumped is not None
    assert (jumped.warm, jumped.dark, jumped.dark_why) == (0.0, 0.0, "")


def test_one_episode_in_a_release_is_a_parsing_slip_and_not_a_series() -> None:
    """Сериалом запись делают НЕСКОЛЬКО серий в раздаче, а не тип записи сам по себе.

    Так в состоянии осела картина, которую ``x264`` в имени сделал первой серией. Парсер
    починен, а записи остались, и строки про серии в выводе фильма быть не должно ни у
    кого. Настоящей раздаче с одной серией это ничего не стоит: переходить всё равно
    некуда.
    """
    one = Entry(title="Картина", magnet="m", kind="tv", season=1, episode=1, episodes=[[1, 1, 0]])

    assert not one.serial
    assert one.label == "", "у не-сериала подписи серии нет"
    assert one.shown_as == "«Картина»"


def test_a_real_series_is_named_with_its_episode_wherever_it_is_shown() -> None:
    """У настоящего сериала подпись серии едет вместе с названием - её видит человек."""
    entry = pack()

    assert entry.serial
    assert entry.label == "s1e2"
    assert entry.shown_as == "«Сериал» s1e2"


def test_an_unknown_key_in_a_saved_record_is_ignored_instead_of_crashing() -> None:
    """Запись, написанную другой версией, читаем молча: лишний ключ - не повод падать.

    Состояние переживает обновления инструмента. Упади чтение на незнакомом поле - человек
    потерял бы все закладки разом из-за одного нового ключа.
    """
    entry = Entry.from_json({"title": "X", "magnet": "m", "совсем_новое_поле": 1})

    assert entry.title == "X"
    assert entry.magnet == "m"
