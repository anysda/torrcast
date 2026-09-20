"""Вышедшая серия, которой нет ни в одной раздаче: поздний приговор и его «не знаю»."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from torrcast.domain.catalogs.web.en import en
from torrcast.domain.catalogs.web.ru import ru
from torrcast.domain.json_value import JsonValue
from torrcast.domain.release import Release
from web.episode_absent import HUNT, WAVE, EpisodeAbsent


@dataclass
class _Episodes:
    """Кэш разбора: чего нет в таблицах - то ещё разбирается, как в живом кэше."""

    tables: dict[str, list[list[int]] | None] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    def table(self, release: Release, _base_url: str) -> list[list[int]] | None:
        self.asked.append(release.magnet)
        return self.tables.get(release.magnet)


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


def _pack(season: int | None, magnet: str) -> Release:
    return Release(raw_name="Show", title="Show", kind="tv", season=season, magnet=magnet)


def _single(season: int, episode: int, magnet: str) -> Release:
    return Release(
        raw_name=f"Show S{season:02d}E{episode:02d}",
        title="Show",
        kind="tv",
        season=season,
        episode=episode,
        magnet=magnet,
    )


def _rows(season: int, *numbers: int, air: int = 0) -> list[JsonValue]:
    episodes: list[JsonValue] = []
    for number in numbers:
        row: dict[str, JsonValue] = {"n": number, "dur": 0.0, "watched": False, "pos": 0.0}
        if air and number >= air:
            row["air"] = "2026-12-31"
        episodes.append(row)
    return [{"n": season, "episodes": episodes}]


def _absent(rows: list[JsonValue], season: int) -> Any:
    row = next(cast(dict[str, Any], r) for r in rows if cast(dict[str, Any], r)["n"] == season)
    return row.get("absent")


def test_a_season_no_release_covers_goes_grey_at_once_without_asking_torrserver() -> None:
    """Сезона нет ни в одной раздаче - это видно по именам, перебирать нечего."""
    episodes = _Episodes()

    rows, hunting = EpisodeAbsent().of(
        _rows(5, 1, 2), "tv:show", 5, [_pack(1, "magnet:first")], episodes, "http://ts"
    )

    assert (_absent(rows, 5), hunting, episodes.asked) == ([1, 2], False, [])


def test_an_unparsed_pack_leaves_the_row_alive_and_the_card_still_looking() -> None:
    """Раздача ещё ничего не сказала: приговора нет, а тело остаётся недоехавшим."""
    episodes = _Episodes()

    rows, hunting = EpisodeAbsent().of(
        _rows(5, 1, 2), "tv:show", 5, [_pack(5, "magnet:fifth")], episodes, "http://ts"
    )

    assert (_absent(rows, 5), hunting, episodes.asked) == (None, True, ["magnet:fifth"])


def test_an_aired_episode_missing_from_every_parsed_release_goes_grey() -> None:
    episodes = _Episodes({"magnet:fifth": [[5, 1], [5, 2]]})

    rows, hunting = EpisodeAbsent().of(
        _rows(5, 1, 2, 3), "tv:show", 5, [_pack(5, "magnet:fifth")], episodes, "http://ts"
    )

    assert (_absent(rows, 5), hunting) == ([3], False)


def test_a_release_that_names_the_episode_keeps_the_row_and_costs_no_parse() -> None:
    """Имя раздачи «S05E03» отвечает за серию само: спрашивать её файлы незачем."""
    episodes = _Episodes({"magnet:fifth": [[5, 1], [5, 2]]})
    pool = [_pack(5, "magnet:fifth"), _single(5, 3, "magnet:third")]

    rows, hunting = EpisodeAbsent().of(_rows(5, 3), "tv:show", 5, pool, episodes, "http://ts")

    assert (_absent(rows, 5), hunting, episodes.asked) == (None, False, [])


def test_a_release_without_numbering_never_becomes_a_verdict() -> None:
    """Пустая таблица - «не знаю», а не «серий нет»: гасить по ней нельзя вовсе."""
    episodes = _Episodes({"magnet:fifth": []})

    rows, hunting = EpisodeAbsent().of(
        _rows(5, 1), "tv:show", 5, [_pack(5, "magnet:fifth")], episodes, "http://ts"
    )

    assert (_absent(rows, 5), hunting) == (None, False)


def test_a_search_that_never_answers_stops_holding_the_page_after_the_deadline() -> None:
    """Упавший разбор переспрашивается вечно: страницу он держит не дольше :data:`HUNT`."""
    clock, episodes = _Clock(), _Episodes()
    absent = EpisodeAbsent(clock=clock)
    pool = [_pack(5, "magnet:fifth")]

    _rows_first, early = absent.of(_rows(5, 1), "tv:show", 5, pool, episodes, "http://ts")
    clock.now = HUNT + 1.0
    rows, late = absent.of(_rows(5, 1), "tv:show", 5, pool, episodes, "http://ts")

    assert (early, late, _absent(rows, 5)) == (True, False, None)


def test_one_answer_starts_no_more_than_a_wave_of_parses() -> None:
    """Веер на весь пул положил бы и рой, и машину показа: пул проходится волнами."""
    episodes = _Episodes()
    pool = [_pack(5, f"magnet:{number}") for number in range(WAVE + 3)]

    _rows_out, hunting = EpisodeAbsent().of(_rows(5, 1), "tv:show", 5, pool, episodes, "http://ts")

    assert (len(episodes.asked), hunting) == (WAVE, True)


def test_a_bookmark_row_is_never_judged() -> None:
    """Строку закладки играет раздача закладки, и в пуле её может не быть вовсе."""
    episodes = _Episodes({"magnet:fifth": [[5, 1]]})
    saved: dict[int, list[JsonValue]] = {5: [{"n": 2, "dur": 0.0, "watched": False, "pos": 0.0}]}

    rows, hunting = EpisodeAbsent().of(
        _rows(5, 1, 2), "tv:show", 5, [_pack(5, "magnet:fifth")], episodes, "http://ts", saved
    )

    assert (_absent(rows, 5), hunting) == (None, False)


def test_an_unreleased_row_is_left_to_its_own_date() -> None:
    episodes = _Episodes({"magnet:fifth": [[5, 1]]})

    rows, _hunting = EpisodeAbsent().of(
        _rows(5, 1, 2, air=2), "tv:show", 5, [_pack(5, "magnet:fifth")], episodes, "http://ts"
    )

    assert _absent(rows, 5) is None


def test_a_list_numbered_unlike_the_releases_gets_no_verdict() -> None:
    """Сквозной номер строки таблицам раздач неизвестен: судить его нечем."""
    episodes = _Episodes()

    rows, hunting = EpisodeAbsent().of(
        _rows(1, 61), "tv:show", 1, [_pack(1, "magnet:first")], episodes, "http://ts", None, True
    )

    assert (_absent(rows, 1), hunting, episodes.asked) == (None, False, [])


def _page() -> str:
    return (Path(__file__).resolve().parents[1] / "web/static/card-series.js").read_text("utf-8")


def test_the_page_keeps_the_row_clickable_until_the_verdict_and_then_says_why() -> None:
    """Звено страницы: JavaScript-рантайма в гейте нет, договор держится текстом.

    Гаснет строка по приговору сезона, до него она обычная, а погасшая объясняет себя
    словом каталога, а не пустой серой полосой.
    """
    page = _page()
    body = page.split("  episodes(data, seasonIndex, key, query) {", 1)[1].split("\n  },", 1)[0]

    assert "const absent = new Set(Array.isArray(season.absent) ? season.absent : []);" in body
    assert "const gone = !coming && absent.has(episode.n);" in body
    assert "const grey = coming || (gone && hold === 0);" in body
    assert "if (!grey) row.addEventListener('click', play);" in body
    assert "} else if (gone && !hold) {\n        meta.appendChild(TCCardSeries._why());" in body
    assert "none.textContent = TC.say('web.detail.episode_absent');" in page
    assert {"web.detail.episode_absent"} <= set(ru()) & set(en())


def test_the_page_holds_the_click_window_open_for_ten_seconds() -> None:
    """Приговор бывает бесплатным и приезжает первым телом: гашение ждёт окно нажатия.

    Иначе строка гасла на четвёртой секунде, и нажатие человека, видевшего её живой,
    съедалось гашением.
    """
    page = _page()
    body = page.split("  episodes(data, seasonIndex, key, query) {", 1)[1].split("\n  },", 1)[0]

    assert "GREY_AFTER: 10000," in page
    assert "const hold = Math.max(0, TCCardSeries.GREY_AFTER - TCCardSeries._sinceOpen());" in body
    assert "if (gone && hold) setTimeout(() => TCCardSeries._fade(row, play), hold);" in body
    # Окно считается от ОТКРЫТИЯ карточки, а не от добора: иначе опрос продлевал бы его.
    assert "TCCardSeries._opened.visit !== TCCard._visit" in page
    # Гасящий будильник снимает и нажатие, и фокус: серая строка не остаётся в кольце.
    for line in (
        "row.removeEventListener('click', play);",
        "row.removeAttribute('tabindex');",
        "delete row.dataset.tcFocusable;",
        "meta.prepend(TCCardSeries._why());",
    ):
        assert line in page
