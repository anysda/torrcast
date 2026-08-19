"""Зеркало :mod:`torrcast.domain.entry`: запись состояния показа как чистое значение.

Переходы записи и закладку сторожит набор состояния (``tests/test_state.py``). Здесь -
то, что живёт только в самой записи: доли конца, приложенные к её собственным числам; поля,
которые относятся к файлу и обязаны обнуляться вместе со сменой файла; и признак сериала,
который нельзя выдавать по одной осечке разбора.
"""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.watch_ratios import ENDING_RATIO, WATCHED_RATIO

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


def test_the_watched_mark_falls_exactly_on_its_share_of_the_length() -> None:
    """«Досмотрено» - это доля от ДЛИТЕЛЬНОСТИ, и граница считается досмотренной.

    Мерка решает, предлагать ли продолжение. Опусти её к середине фильма - и человек,
    ушедший на середине, больше не смог бы вернуться в своё место: запись объявила бы
    картину досмотренной и предложила бы начать сначала. Подними выше конца - и закладка
    не закрывалась бы никогда. Поэтому проверяется само отношение позиции к длительности:
    чуть ниже доли - ещё нет, ровно на доле и выше - уже да.
    """
    threshold = WHOLE * WATCHED_RATIO

    assert not movie(pos=threshold * 0.9, dur=WHOLE).watched, "ниже доли - ещё не досмотрено"
    assert movie(pos=threshold, dur=WHOLE).watched, "ровно на доле - уже досмотрено"
    assert movie(pos=WHOLE, dur=WHOLE).watched


def test_the_credits_mark_falls_exactly_on_its_own_share_of_the_length() -> None:
    """«Это был конец, а не обрыв» - тоже доля от длительности, и тоже включающая.

    Ею показ решает, воскрешать ли погасший экран. Опусти долю - и обычный конец фильма
    читался бы как авария: показ полез бы поднимать доигранное. Подними - и настоящий
    обрыв под самый конец сошёл бы за титры, и вечер тихо кончился бы на ровном месте.
    """
    threshold = WHOLE * ENDING_RATIO

    assert not movie(pos=threshold * 0.9, dur=WHOLE).ending, "ниже доли - это обрыв, а не титры"
    assert movie(pos=threshold, dur=WHOLE).ending, "ровно на доле - уже титры"


def test_an_unknown_length_never_gives_the_right_to_guess_the_share() -> None:
    """Без длительности доли считать не от чего, и обе мерки молчат.

    Приёмник знает длину не всегда. Начни запись угадывать - недосмотренный фильм с
    неизвестной длиной уходил бы в «досмотрено», и продолжить его стало бы нечем.
    Отрицательная длина - тот же случай: у картины её не бывает, и считать долю от неё
    значит объявлять концом любое место, включая начало.
    """
    for dur in (0.0, -1.0):
        assert not movie(pos=WHOLE, dur=dur).ending
        assert not movie(pos=WHOLE, dur=dur).watched


def test_continuing_is_offered_only_where_there_is_progress_left_unfinished() -> None:
    """Продолжать можно ровно то, что НАЧАЛИ и не досмотрели, - оба условия сразу.

    Запись, которую ни разу не играли, продолжать не с чего: позиция ноль, и «продолжить»
    отправило бы человека в начало под видом закладки. Досмотренную - тем более: её место
    в конце ленты, и предложение вернуться туда было бы предложением посмотреть титры.
    Ослабь связку до «или» - и обе эти записи стали бы продолжаемыми: свежая, потому что
    не досмотрена, доигранная - потому что позиция у неё есть.
    """
    assert movie(pos=500.0, dur=WHOLE).resumable, "начатое и недосмотренное продолжают"
    assert not movie(pos=0.0, dur=WHOLE).resumable, "нетронутую запись продолжать не с чего"
    assert not movie(pos=500.0, dur=WHOLE, done=True).resumable, "досмотренное не продолжают"


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


def test_an_episode_is_found_by_both_its_numbers_and_a_missing_one_is_said_to_be_missing() -> None:
    """Место серии ищется по СЕЗОНУ И НОМЕРУ разом, а «такой нет» - отдельный ответ.

    По одному сезону в паке нашлась бы первая попавшаяся серия, и прыжок `s1e4` уезжал бы
    на `s1e2`. А спутай «нет такой» с «первая» - и запрос несуществующей серии молча играл
    бы начало раздачи вместо честного отказа, за которым цепочка идёт искать другой релиз.
    """
    series = pack()

    assert series.where(1, 2) == 0
    assert series.where(1, 4) == 2, "серия ищется по обоим числам, а не по одному сезону"
    assert series.where(9, 9) == -1, "серии в раздаче нет - и это отдельный ответ, не ноль"
    assert series.jump(9, 9) is None


def test_the_last_episode_of_a_release_ends_the_show_instead_of_running_off_the_list() -> None:
    """С последней серии переходить некуда: раздача кончилась, и запись это признаёт.

    Считай последнюю серию непоследней - и переход уехал бы за край списка. Признание
    конца тут и есть переход: дальше показ гаснет, а не ищет несуществующую серию.
    """
    last = pack().jump(1, 4)
    assert last is not None

    ended = last.advance()

    assert ended.done, "конец раздачи - это «досмотрено», а не следующая серия"
    assert ended.pos == 0.0
    assert ended.episode == 4, "серия остаётся последней: уходить с неё некуда"


def test_a_broken_row_in_the_saved_episode_list_is_dropped_and_not_half_read() -> None:
    """Строка списка серий без всех трёх чисел теряется целиком, а не читается наполовину.

    Список серий - это «сезон, номер, файл», и по нему идут автопереход и прыжки. Пусти
    внутрь укороченную строку - и переход брал бы номер файла из пустоты: показ уехал бы
    не на ту серию, а то и упал бы на чтении состояния. Потерять битую строку дешевле.
    """
    entry = Entry.from_json(
        {
            "title": "Сериал",
            "magnet": "m",
            "kind": "tv",
            "episodes": [[1, 1, 0], [1, 2], "мусор", [1, 3, 7]],
        }
    )

    assert entry.episodes == [[1, 1, 0], [1, 3, 7]]


def test_an_unknown_key_in_a_saved_record_is_ignored_instead_of_crashing() -> None:
    """Запись, написанную другой версией, читаем молча: лишний ключ - не повод падать.

    Состояние переживает обновления инструмента. Упади чтение на незнакомом поле - человек
    потерял бы все закладки разом из-за одного нового ключа.
    """
    entry = Entry.from_json({"title": "X", "magnet": "m", "совсем_новое_поле": 1})

    assert entry.title == "X"
    assert entry.magnet == "m"
