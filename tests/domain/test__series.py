"""Зеркало :mod:`torrcast.domain._series`: серии выбранной раздачи как чистое правило.

Разбор имён и две системы нумерации сторожит набор разбора (``tests/test_series.py``).
Здесь - то, за что отвечает сама единица: она ничего не запоминает на себе, отдаёт файл по
номеру ИЗ РАЗДАЧИ, а не по месту в разобранном списке, и говорит о промахе так, чтобы
человеку было что делать дальше.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from torrcast.domain._series import _Series
from torrcast.domain.episode import Episode
from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile

GB = 1024**3


def season_release(season: int) -> Release:
    """Раздача, назвавшая свой сезон: обычный случай подписанного сезона."""
    return Release(raw_name=f"Сериал S{season:02d} 1080p", title="Сериал", season=season, kind="tv")


def season_files(season: int, count: int) -> list[TorrFile]:
    """Файлы одного сезона, как их отдаёт служба раздач: сквозной номер и путь."""
    return [
        TorrFile(index, f"Сериал/Сериал.S{season:02d}E{n:02d}.mkv", GB)
        for index, n in enumerate(range(1, count + 1), start=1)
    ]


def test_the_wanted_episode_is_returned_by_its_number_inside_the_release() -> None:
    """Отдаётся файл раздачи, а не элемент разобранного списка.

    Разбор выкидывает из списка чужое - субтитры, ролики, сэмплы, - поэтому места в нём и
    номера в раздаче не совпадают. Возьми показ элемент по месту - и играл бы он не ту
    серию, о которой просили, причём молча.
    """
    files = season_files(1, 5)
    chosen = _Series(want=Episode(1, 4)).choose(season_release(1), files)

    assert chosen.index == 4
    assert "E04" in chosen.name
    assert chosen in files, "вернуть надо файл самой раздачи, а не его пересобранную копию"


def test_the_lookup_carries_nothing_but_the_episode_it_was_asked_about() -> None:
    """Разбор НИЧЕГО не запоминает на себе, и это видно по составу самой единицы.

    Один и тот же разбор живёт на всю картину, а спрашивают его параллельно: подготовка
    греет впрок и запасные раздачи, и каждая зовёт его из своего потока. Появись у него
    второе поле - список серий картины оставляла бы ПОСЛЕДНЯЯ ответившая раздача, а не та,
    которую играют: у пака в состояние уезжал пустой список от запасной раздачи, и сериал
    переставал быть сериалом - автоперехода на следующую серию не было вовсе.
    """
    assert [field.name for field in fields(_Series)] == ["want"]


def test_two_releases_asked_in_turn_answer_independently_of_each_other() -> None:
    """Ответ про серию зависит от поданных файлов, а не от прошлого вопроса.

    Ровно так разбор и зовут: подряд, из разных потоков, про разные раздачи одной картины.
    """
    lookup = _Series(want=Episode(1, 2))
    long_pack = season_files(1, 12)
    short_pack = season_files(1, 3)

    assert lookup.choose(season_release(1), long_pack).name.endswith("E02.mkv")
    assert lookup.choose(season_release(1), short_pack).name.endswith("E02.mkv")
    assert _Series.table(long_pack, 1) != _Series.table(short_pack, 1)


def test_a_missing_episode_is_refused_with_a_list_and_a_way_out() -> None:
    """Отказ обязан назвать, чего именно нет, что есть, и что человеку делать дальше.

    Голое «серии нет» тупиково: непонятно, промахнулась раздача или запрос, и куда идти.
    Поэтому в строке стоят и просимая серия, и содержимое раздачи, и способ взять другую.
    """
    with pytest.raises(NotFoundError) as refusal:
        _Series(want=Episode(1, 9)).choose(season_release(1), season_files(1, 3))

    said = str(refusal.value)
    assert "s1e9" in said
    assert "серий 3: s1e1...s1e3" in said
    assert "--release" in said


def test_the_summary_of_a_pack_names_the_span_of_its_seasons() -> None:
    """У пака человеку важен размах сезонов, у одного сезона он лишний.

    Без размаха пак и один сезон выглядят одинаково - «серий 24», - и по такой строке
    нельзя понять, лежит ли просимый сезон в этой раздаче вообще.
    """
    one_season = [EpisodeFile(n, 1, n, f"s1e{n}.mkv") for n in range(1, 4)]
    pack = one_season + [EpisodeFile(n + 3, 2, n, f"s2e{n}.mkv") for n in range(1, 4)]

    assert _Series.summary(one_season) == "серий 3: s1e1...s1e3"
    assert _Series.summary(pack) == "сезоны 1-2 · серий 6: s1e1...s2e3"


def test_a_release_with_nothing_recognisable_says_so_instead_of_pretending() -> None:
    """Пустой список серий - это «серий не нашлось», а не «серий 0» и не пустая строка.

    Строку читает человек в отказе. Промолчи она - он увидел бы «серии нет ()» и не узнал
    бы, что раздача вообще не про серии.
    """
    assert _Series.summary([]) == "серий не нашлось"


def test_the_episode_table_is_a_plain_list_of_numbers_for_the_state() -> None:
    """Таблица серий уходит в состояние, и по ней идут автопереход и прыжки.

    Это строки «сезон, серия, номер файла, размер файла» и ничего больше: состояние -
    файл на диске, и класть в него объекты разбора нельзя, а номер и размер обязаны быть
    от того же файла раздачи.
    """
    table = _Series.table(season_files(1, 3), 1)

    assert table == [
        [1, 1, 1, 1024**3],
        [1, 2, 2, 1024**3],
        [1, 3, 3, 1024**3],
    ]


def crosswise_release() -> Release:
    """Раздача со СКВОЗНЫМ счётом: серии перечислены, а сезон не назван ни один."""
    return Release(
        raw_name="Сериал [202-252]",
        title="Сериал",
        kind="tv",
        episodes=tuple(range(202, 253)),
    )


def crosswise_files() -> list[TorrFile]:
    """Файлы сквозного куска: в именах сквозные номера, сезона в них нет."""
    return [
        TorrFile(index, f"Сериал/Сериал.E{n:03d}.mkv", GB)
        for index, n in enumerate(range(202, 253), start=1)
    ]


def test_a_release_counting_straight_through_names_both_numberings_instead_of_denying() -> None:
    """У раздачи со сквозным счётом серия, скорее всего, ЕСТЬ - под другим номером.

    🔴 TC-182. У одного сериала сосуществуют две нумерации: часть раздач подписана
    сезонами, часть считает серии насквозь через весь сериал. Ответь такая раздача «серии
    нет» - это была бы неправда дважды: и про наличие, и про причину, - и человек ушёл бы
    искать то, что лежит перед ним. Пересчитать сезон в сквозной номер честно нельзя:
    границ сезонов не назвало ни одно имя. Поэтому называются ОБЕ системы и сам диапазон.
    """
    with pytest.raises(NotFoundError) as refusal:
        _Series(want=Episode(5, 1)).choose(crosswise_release(), crosswise_files())

    said = str(refusal.value)
    assert "нумерации разные" in said
    assert "202-252" in said, "диапазон сквозного счёта обязан быть назван"
    assert "--release" in said, "человеку сказано, чем это лечится"


def test_the_first_season_is_never_explained_by_a_second_numbering() -> None:
    """Про ПЕРВЫЙ сезон разговора о двух нумерациях нет: там пересчитывать нечего.

    Сквозной счёт расходится с посезонным начиная со второго сезона - первый у обеих
    систем начинается с одного места. Объясни промах первого сезона чужой нумерацией - и
    человек искал бы другую раздачу вместо того, чтобы узнать, что серии правда нет.
    """
    with pytest.raises(NotFoundError) as refusal:
        _Series(want=Episode(1, 999)).choose(crosswise_release(), crosswise_files())

    assert "нумерации разные" not in str(refusal.value)


def test_a_release_that_named_its_season_is_never_accused_of_counting_straight() -> None:
    """Раздача, назвавшая сезон, считает по сезонам - и промах у неё обычный.

    Признак сквозного счёта - молчание про сезон, а не наличие списка серий. Спутай их -
    и подписанная сезоном раздача отправляла бы человека искать «раздачу, подписанную
    сезоном», то есть ровно ту, которую он уже держит.
    """
    named = Release(
        raw_name="Сериал S05 1080p", title="Сериал", kind="tv", season=5, episodes=(1, 2, 3)
    )

    with pytest.raises(NotFoundError) as refusal:
        _Series(want=Episode(5, 99)).choose(named, season_files(5, 3))

    assert "нумерации разные" not in str(refusal.value)


def test_a_release_that_listed_its_seasons_is_never_accused_of_counting_straight() -> None:
    """Пак, перечисливший сезоны, тоже считает по сезонам, даже не назвав один главный.

    Сезоны, перечисленные именем, - такое же называние системы, как и один сезон. Оставь
    его без внимания - и пак сезонов объяснял бы промах чужой нумерацией.
    """
    pack_of_seasons = Release(
        raw_name="Сериал S01-S03 1080p",
        title="Сериал",
        kind="tv",
        seasons=(1, 2, 3),
        episodes=tuple(range(202, 253)),
    )

    with pytest.raises(NotFoundError) as refusal:
        _Series(want=Episode(5, 1)).choose(pack_of_seasons, crosswise_files())

    assert "нумерации разные" not in str(refusal.value)
