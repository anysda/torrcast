"""Зеркало :mod:`torrcast.usecases.choice.last_hope_note`: строка про последнюю надежду.

Человек обязан услышать не только «перекодирую целиком», но и ПОЧЕМУ выбран дорогой
путь: иначе «Гинтама» на HEVC и «Гинтама» на честном 1080p выглядят с экрана одинаково,
а стоят разного.
"""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.choice.world import film, plan
from torrcast.domain._series import _Series
from torrcast.domain.episode import Episode
from torrcast.usecases.choice.last_hope_note import last_hope_note

HEVC = film("Гинтама S01E01 BDRip HEVC 720p", seeders=4, codec="HEVC", quality="720p")
HONEST = film("Гинтама S01E01 WEB-DL 1080p", seeders=5)


def test_the_line_names_the_episode_for_which_no_honest_release_was_left() -> None:
    """Строка называет серию: у сериала носитель кончается посерийно, а не картиной."""
    gintama = replace(
        plan("Гинтама", 2006, kind="tv", pool=[HEVC], last_resort=True),
        series=_Series(want=Episode(1, 1)),
    )

    said = last_hope_note(gintama, HEVC)

    assert said == "живой раздачи серии s1e1 без HEVC нет - беру HEVC последней надеждой"


def test_a_film_has_no_episode_to_name_and_the_line_speaks_of_the_picture() -> None:
    """Серии не спрашивали - речь про картину целиком, и выдумывать номер нечего."""
    film_plan = plan("Кино", 2020, pool=[HEVC], last_resort=True)

    assert last_hope_note(film_plan, HEVC) == (
        "живой раздачи картины без HEVC нет - беру HEVC последней надеждой"
    )


def test_the_usual_path_says_nothing_because_there_is_no_price_to_explain() -> None:
    """Ворота последней надежды закрыты - путь обычный, и строки нет.

    Скажи она своё и тут - «последняя надежда» превратилась бы в шум на каждом показе,
    и настоящая потерялась бы среди него.
    """
    ordinary = plan("Кино", 2020, pool=[HEVC])

    assert last_hope_note(ordinary, HEVC) == ""


def test_an_honest_release_taken_through_open_gates_is_not_a_last_hope() -> None:
    """Ворота открыты, но играет честный H.264 - платить за него дорогим путём не надо.

    Строка про надежду тут была бы неправдой ровно наоборот: она обещала бы сплошной
    перекод там, где поедет копия.
    """
    gintama = plan("Гинтама", 2006, kind="tv", pool=[HONEST, HEVC], last_resort=True)

    assert last_hope_note(gintama, HONEST) == ""
