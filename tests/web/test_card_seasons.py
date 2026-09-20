"""Карточка сериала собирает вкладки и серии из разных раздач."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, cast

from torrcast.domain._series import _Series
from torrcast.domain.entry import Entry
from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.card_seasons import card_seasons


@dataclass
class _Episodes:
    tables: dict[str, list[list[int]] | None]
    asked: list[str]

    def table(self, release: Release, _base_url: str) -> list[list[int]] | None:
        """Как живой кэш: неизвестная раздача - это «разбор ещё идёт», а не отказ."""
        self.asked.append(release.magnet)
        return self.tables.get(release.magnet)


def _release(number: int, magnet: str) -> Release:
    return Release(
        raw_name=f"Show / Сезон: {number} WEB-DL 1080p",
        title="Show",
        kind="tv",
        season=number,
        magnet=magnet,
    )


def _plan() -> tuple[Plan, Release, Release]:
    first, second = _release(1, "magnet:first"), _release(2, "magnet:second")
    picture = Picture(title="Show", year=2022, kind="tv", releases=[first, second])
    return Plan(picture=picture, ranked=[first], runtime=1500.0, warn_mbit=12.0), first, second


def _rows(seasons: list[Any]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], seasons)


def test_tabs_are_the_union_and_the_selected_season_uses_its_own_release() -> None:
    plan, first, second = _plan()
    episodes = _Episodes({first.magnet: [[1, 1]], second.magnet: [[2, 1], [2, 2]]}, [])

    seasons, partial, release, _layout = card_seasons(
        plan, None, "http://torrserver", episodes, season=2
    )

    assert partial is False
    rows = _rows(seasons)
    assert [row["n"] for row in rows] == [1, 2]
    assert rows[0]["episodes"] == []
    assert [row["n"] for row in rows[1]["episodes"]] == [1, 2]
    assert episodes.asked == [second.magnet]
    assert release is second


def test_bookmark_keeps_every_pool_season_and_does_not_choose_its_release_for_another_one() -> None:
    plan, first, second = _plan()
    entry = Entry(
        "Show",
        second.magnet,
        kind="tv",
        season=2,
        episode=2,
        episodes=[[2, 1, 0, 0], [2, 2, 1, 0]],
    )
    episodes = _Episodes({first.magnet: [[1, 1]], second.magnet: [[2, 1], [2, 2]]}, [])

    seasons, partial, release, _layout = card_seasons(
        plan, entry, "http://torrserver", episodes, season=1
    )

    assert partial is False
    rows = _rows(seasons)
    assert [row["n"] for row in rows] == [1, 2]
    assert [row["n"] for row in rows[0]["episodes"]] == [1]
    assert [row["n"] for row in rows[1]["episodes"]] == [1, 2]
    assert episodes.asked == [first.magnet]
    assert release is first


def test_without_a_chosen_tab_the_bookmark_season_gets_its_file_table() -> None:
    plan, first, second = _plan()
    entry = Entry("Show", second.magnet, kind="tv", season=2, episode=1, episodes=[[2, 1, 0, 0]])
    episodes = _Episodes({first.magnet: [[1, 1]], second.magnet: [[2, 1], [2, 2]]}, [])

    seasons, partial, release, _layout = card_seasons(plan, entry, "http://torrserver", episodes)

    assert partial is False
    assert episodes.asked == [second.magnet]
    assert [row["n"] for row in _rows(seasons)] == [1, 2]
    assert release is second


def test_the_bookmark_release_beats_a_ranked_pack_for_its_opened_season() -> None:
    plan, first, second = _plan()
    second = replace(second, magnet="magnet:?xt=urn:btih:" + "a" * 40)
    plan.picture.releases[1] = second
    pack = Release(raw_name="Show Complete", title="Show", kind="tv", magnet="magnet:pack")
    plan.picture.releases.append(pack)
    ranked = replace(plan, ranked=[pack, first])
    entry = Entry("Show", second.magnet, kind="tv", season=2, episode=1, episodes=[[2, 1, 0, 0]])
    episodes = _Episodes({second.magnet: [[2, 1]], pack.magnet: [[1, 1], [2, 1]]}, [])

    _seasons, _partial, release, _layout = card_seasons(
        ranked, entry, "http://torrserver", episodes
    )

    assert episodes.asked == [second.magnet]
    assert release is second


def test_every_season_in_the_bookmark_rows_lists_and_names_the_bookmark_pack() -> None:
    """Строки второго сезона приходят из закладки-пака, и раздачу вкладке называет она же."""
    plan, first, second = _plan()
    pack = Release(
        raw_name="Show [S01-02]",
        title="Show",
        kind="tv",
        seasons=(1, 2),
        magnet="magnet:?xt=urn:btih:" + "c" * 40,
    )
    plan.picture.releases.append(pack)
    plan = replace(plan, ranked=[second, first, pack])
    rows = [[1, 1, 0, 0], [1, 2, 0, 0], [2, 1, 0, 0], [2, 2, 0, 0]]
    entry = Entry("Show", pack.magnet, kind="tv", season=1, episode=2, episodes=rows)
    tables = {first.magnet: [[1, 1]], second.magnet: [[2, 1], [2, 2], [2, 3]], pack.magnet: rows}
    episodes = _Episodes(cast(dict[str, list[list[int]] | None], tables), [])

    seasons, _partial, release, _layout = card_seasons(
        plan, entry, "http://torrserver", episodes, 2
    )

    assert [row["n"] for row in _rows(seasons)[1]["episodes"]] == [1, 2]
    assert release is pack


def test_a_merged_spinoff_does_not_become_a_tab_of_the_opened_show() -> None:
    plan, first, second = _plan()
    short = replace(_release(5, "magnet:short"), title="Show Shorts")
    plan.picture.releases.append(short)
    episodes = _Episodes({first.magnet: [[1, 1]], second.magnet: [[2, 1]]}, [])

    seasons, partial, _selected, _layout = card_seasons(plan, None, "http://torrserver", episodes)

    assert partial is False
    assert [row["n"] for row in _rows(seasons)] == [1, 2]


class _Files:
    def table(self, _release: Release, _base_url: str) -> list[list[int]] | None:
        return [[1, 1], [1, 2], [2, 1], [3, 1]]


def _single(release: Release) -> Plan:
    picture = Picture(title="Show", year=2013, kind="tv", releases=[release])
    return Plan(picture=picture, ranked=[release], runtime=1500.0, warn_mbit=12.0)


def test_a_full_pack_without_a_season_in_its_name_gets_tabs_from_its_files() -> None:
    pack = Release(raw_name="Show / Complete [2013-2023]", title="Show", kind="tv", magnet="m:p")

    seasons, partial, release, _layout = card_seasons(
        _single(pack), None, "http://torrserver", _Files()
    )

    assert partial is False
    assert [row["n"] for row in _rows(seasons)] == [1, 2, 3]
    assert release is pack


def test_files_of_a_named_season_add_the_seasons_they_hold() -> None:
    seasons, _, _, _layout = card_seasons(
        _single(_release(1, "m:one")), None, "http://torrserver", _Files()
    )

    assert [row["n"] for row in _rows(seasons)] == [1, 2, 3]


def test_the_opened_season_lists_the_release_the_show_would_play() -> None:
    plan, first, _second = _plan()
    pack = Release(raw_name="Show / Complete", title="Show", kind="tv", magnet="magnet:pack")
    plan.picture.releases.append(pack)
    ranked = replace(plan, ranked=[pack, first])
    episodes = _Episodes({pack.magnet: [[1, 1], [2, 1]], first.magnet: [[1, 1]]}, [])

    card_seasons(ranked, None, "http://torrserver", episodes)

    assert episodes.asked == [pack.magnet]


def test_a_season_outside_the_card_ranking_lists_the_release_its_ranking_puts_first() -> None:
    """Чужой сезон берёт раздачу своим порядком отбора, а не выдачи и не сезона карточки."""
    plan, first, _second = _plan()
    gib = 1024**3
    phone = Release(
        raw_name="Show [S01-05] WEB-DL-AVC КПК",
        title="Show",
        kind="tv",
        seasons=(1, 2, 3, 4, 5),
        quality="360p",
        codec="H.264",
        voices=("rus",),
        size=4 * gib,
        seeders=9,
        magnet="magnet:phone",
    )
    full_hd = replace(
        phone,
        raw_name="Show [S01-07] BDRip 1080p",
        quality="1080p",
        size=60 * gib,
        seeders=140,
        magnet="magnet:full-hd",
    )
    plan.picture.releases[:] = [first, phone, full_hd]
    # Отбор карточки судил первый сезон и поставил телефонную раздачу выше: второй сезон
    # этот порядок не наследует.
    plan = replace(plan, ranked=[phone, full_hd, first], series=_Series(want=Episode(1, 1)))
    episodes = _Episodes({phone.magnet: [[2, 1]], full_hd.magnet: [[2, 1]]}, [])

    card_seasons(plan, None, "http://torrserver", episodes, season=2)

    assert episodes.asked == [full_hd.magnet]


def test_a_bookmark_release_gone_from_the_pool_is_not_swapped_for_the_first_ranked() -> None:
    """🔴 Раздачи закладки не было в пуле с диска: вкладка молча назвала первую по рангу."""
    plan, _first, second = _plan()
    kept = "magnet:?xt=urn:btih:" + "e" * 40
    entry = Entry("Show", kept, kind="tv", season=2, episode=1, episodes=[[2, 1, 0, 0]])
    episodes = _Episodes({kept: [[2, 1], [2, 2]], second.magnet: [[2, 1]]}, [])

    _seasons, partial, release, _layout = card_seasons(plan, entry, "http://torrserver", episodes)

    assert release is not None and release.magnet == kept and release.season == 2
    assert release not in plan.picture.releases
    assert (episodes.asked, partial) == ([kept], False)


@dataclass
class _Catalog:
    known: dict[int, list[Any]]
    pending: bool = False
    layout: list[int] | None = None

    def rows(
        self, _picture: Picture, _releases: Any, saved: dict[int, list[Any]]
    ) -> tuple[dict[int, list[Any]], bool, list[int]]:
        return {**self.known, **saved}, self.pending, self.layout or []


def _blank(*numbers: int) -> list[Any]:
    return [{"n": n, "dur": 0.0, "watched": False, "pos": 0.0} for n in numbers]


def test_a_catalogued_series_shows_every_season_and_episode_without_torrserver() -> None:
    plan, _first, second = _plan()
    episodes = _Episodes({}, [])
    catalog = _Catalog({1: _blank(1, 2), 2: _blank(1, 2, 3), 3: _blank(1)}, pending=True)

    seasons, partial, release, _layout = card_seasons(
        plan, None, "http://torrserver", episodes, 2, catalog=catalog
    )

    rows = _rows(seasons)
    assert [(row["n"], len(row["episodes"])) for row in rows] == [(1, 2), (2, 3), (3, 1)]
    # Раздачу открытого сезона карточка всё же спрашивает - но не ради строк, а ради
    # приговора «серии нет ни в одной раздаче» (:mod:`web.episode_absent`), и ответа
    # не ждёт: строки уже целые, а приговор приедет следующим добором.
    assert (episodes.asked, partial, release) == ([second.magnet], True, second)
    assert all("absent" not in row for row in rows)


def test_a_list_numbered_unlike_the_releases_keeps_only_its_own_tabs_interns() -> None:
    """Раздачи зовут сезоны 1 и 2, список IMDb один сезон из 3: вкладка 2 раздач не рисуется."""
    plan, first, _second = _plan()
    episodes = _Episodes({}, [])
    catalog = _Catalog({1: _blank(1, 2, 3)}, layout=[3])

    seasons, partial, release, layout = card_seasons(
        plan, None, "http://ts", episodes, 2, catalog=catalog
    )

    assert [(row["n"], len(row["episodes"])) for row in _rows(seasons)] == [(1, 3)]
    assert (episodes.asked, partial, release, layout) == ([], False, first, [3])


def test_a_pool_season_the_catalogue_does_not_know_yet_still_reads_its_files() -> None:
    first = _release(1, "magnet:first")
    fresh = _release(4, "magnet:fresh")
    plan = Plan(
        picture=Picture(title="Show", year=2022, kind="tv", releases=[first, fresh]),
        ranked=[first],
        runtime=1500.0,
        warn_mbit=12.0,
    )
    episodes = _Episodes({fresh.magnet: [[4, 1], [4, 2]]}, [])
    catalog = _Catalog({1: _blank(1), 2: _blank(1)})

    seasons, partial, _, _layout = card_seasons(
        plan, None, "http://ts", episodes, 4, catalog=catalog
    )

    assert [(row["n"], len(row["episodes"])) for row in _rows(seasons)] == [(1, 1), (2, 1), (4, 2)]
    assert (episodes.asked, partial) == ([fresh.magnet], False)


def test_a_pool_season_the_catalogue_skips_keeps_its_tab() -> None:
    """Раздача зовёт сезон 2, каталог знает 1 и 3: вкладка 2 остаётся, как без каталога."""
    plan, _first, second = _plan()
    episodes = _Episodes({second.magnet: [[2, 1], [2, 2]]}, [])
    catalog = _Catalog({1: _blank(1), 3: _blank(1)})

    seasons, _partial, _, _layout = card_seasons(
        plan, None, "http://ts", episodes, 2, catalog=catalog
    )

    assert [(row["n"], len(row["episodes"])) for row in _rows(seasons)] == [(1, 1), (2, 2), (3, 1)]


def test_a_season_the_ranked_pack_holds_no_files_for_lists_the_release_that_names_it() -> None:
    """«Универ. Новая общага»: пак без сезона в имени держит s01-s04, сезон 5 зовёт «[S05]»."""
    plan, first, _second = _plan()
    pack = Release(raw_name="Show 1080p", title="Show", kind="tv", magnet="magnet:pack")
    fifth = _release(5, "magnet:fifth")
    plan.picture.releases.extend([pack, fifth])
    episodes = _Episodes({pack.magnet: [[1, 1], [4, 1]], fifth.magnet: None}, [])
    ranked = replace(plan, ranked=[pack, first, fifth])

    _seasons, partial, release, _layout = card_seasons(ranked, None, "http://ts", episodes, 5)
    episodes.tables[fifth.magnet] = [[5, 1], [5, 2]]
    seasons, again, chosen, _layout = card_seasons(ranked, None, "http://ts", episodes, 5)

    assert (partial, release, again, chosen) == (True, fifth, False, fifth)
    assert [len(row["episodes"]) for row in _rows(seasons) if row["n"] == 5] == [2]


def test_a_catalogued_aired_episode_goes_grey_only_after_the_releases_answer() -> None:
    """Серия каталога, которой нет в раздаче: сначала обычная строка, приговор - позже.

    Перебор раздач карточку не держит (TC-1250): первый ответ приходит с целыми строками
    и пометкой недоехавшего тела, а ``absent`` приезжает следующим добором страницы.
    """
    plan, _first, second = _plan()
    episodes = _Episodes({}, [])
    catalog = _Catalog({2: _blank(1, 2, 3)})

    early, looking, _release, _layout = card_seasons(
        plan, None, "http://ts", episodes, 2, catalog=catalog
    )
    episodes.tables[second.magnet] = [[2, 1], [2, 2]]
    late, settled, _chosen, _rest = card_seasons(
        plan, None, "http://ts", episodes, 2, catalog=catalog
    )

    assert (looking, settled) == (True, False)
    assert all("absent" not in row for row in _rows(early)), "строка погасла до ответа раздач"
    assert [row.get("absent") for row in _rows(late) if row["n"] == 2] == [[3]]
    assert [len(row["episodes"]) for row in _rows(late) if row["n"] == 2] == [3]


def test_a_tab_whose_releases_hold_no_episode_says_so_instead_of_showing_nothing() -> None:
    """Разбор договорил и не нашёл ни одной серии: вкладка помечена, а не молчит.

    «Классический Доктор Кто» рисовал тринадцать вкладок, за девятью из них не было ни
    строки, ни слова. Метку получает только открытый сезон: остальные пусты потому, что
    их никто не разбирал, и «не знаю» выдавать за «нет» нельзя.
    """
    plan, _first, second = _plan()
    episodes = _Episodes({second.magnet: []}, [])

    seasons, partial, release, _layout = card_seasons(
        plan, None, "http://torrserver", episodes, season=2
    )

    assert (partial, release) == (False, second)
    assert [row.get("empty") for row in _rows(seasons) if row["n"] == 2] == [True]
    assert [row.get("empty") for row in _rows(seasons) if row["n"] == 1] == [None], "чужой сезон"


def test_a_tab_still_being_parsed_is_not_called_empty() -> None:
    """Таблица раздачи не доехала: это «не знаю», и слова «серий не нашлось» тут нет."""
    plan, _first, second = _plan()
    episodes = _Episodes({}, [])

    seasons, partial, release, _layout = card_seasons(
        plan, None, "http://torrserver", episodes, season=2
    )

    assert (partial, release) == (True, second)
    assert all(row.get("empty") is None for row in _rows(seasons))


def test_the_page_draws_the_empty_season_note_and_both_catalogs_carry_the_word() -> None:
    """Слово пустой вкладки есть на странице и в обоих языках: молчащая метка не метка."""
    from pathlib import Path

    from torrcast.domain.catalogs.web.en import en
    from torrcast.domain.catalogs.web.ru import ru

    page = Path(__file__).resolve().parents[2] / "web" / "static" / "card-series.js"
    body = page.read_text(encoding="utf-8")

    assert "if (!season.episodes.length && season.empty) {" in body
    assert "none.textContent = TC.say('web.detail.season_absent');" in body
    assert {"web.detail.season_absent"} <= set(ru()) & set(en())
