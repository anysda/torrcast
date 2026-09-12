"""RelatedLookup: родня по франшизе в фоне, кэш на процесс, форма - как у плитки полок."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.origin import Origin
from torrcast.domain.json_value import JsonValue
from web.related_lookup import SILENT, RelatedLookup

_ONE = Kin("Q1", "Гарри Поттер и Тайная комната", 2002)
_TWO = Kin("Q2", "Гарри Поттер и Кубок огня", 2005)


def _sync(job: Callable[[], None]) -> None:
    job()


def _passthrough(records: list[JsonValue]) -> list[JsonValue]:
    return records


def test_the_first_ask_starts_the_background_build_and_answers_none_when_still_slow() -> None:
    """Фон не успевает - вопрос честно висит: ``None``, а не выдуманный список."""
    lookup = RelatedLookup(
        franchise=lambda *_a: [_ONE, _TWO], offer=_passthrough, spawn=lambda _job: None
    )

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is None


def test_a_synchronous_build_answers_the_very_same_call_with_tiles_shaped_like_shelves() -> None:
    """Фон синхронный (тест) - плитки родни готовы уже к первому ответу, в форме полки."""
    lookup = RelatedLookup(franchise=lambda *_a: [_ONE, _TWO], offer=_passthrough, spawn=_sync)

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is not None
    assert len(related) == 2
    first = related[0]
    assert isinstance(first, dict)
    assert set(first) == {"key", "title", "shown", "year", "kind", "quality", "poster", "query"}
    assert first["title"] == "Гарри Поттер и Тайная комната"
    assert first["shown"] == "Гарри Поттер и Тайная комната"
    assert first["kind"] == "movie"
    assert first["key"] == "movie:гарри-поттер-и-тайная-комната:2002"
    assert first["query"] == "Гарри Поттер и философский камень"


def test_an_empty_franchise_is_a_finished_answer_not_a_pending_one() -> None:
    """Родни у картины нет - это законченный пустой ответ, а не «ещё не готово»."""
    lookup = RelatedLookup(franchise=lambda *_a: [], offer=_passthrough, spawn=_sync)

    related = lookup.of("Картина одна на всю франшизу", False)

    assert related == []


def test_a_silent_network_is_not_cached_as_an_empty_shelf() -> None:
    """🔴 ``None`` от франшизы - сеть молчит: не ответ, а недоезд, и кэшировать его
    «родни нет» на :data:`RETRY` нельзя - вопрос после :data:`SILENT` заводит добор заново."""
    asked: list[str] = []
    now = [0.0]

    def _silent(title: str, _series: bool, _timeout: float) -> list[Kin] | None:
        asked.append(title)
        return None

    lookup = RelatedLookup(franchise=_silent, offer=_passthrough, spawn=_sync, clock=lambda: now[0])
    assert lookup.of("Чужой", False) is None
    now[0] += SILENT + 1.0
    assert lookup.of("Чужой", False) is None
    assert asked == ["Чужой", "Чужой"], "вопрос после срока обязан спросить франшизу заново"


def test_silence_is_not_asked_again_on_every_look_and_is_not_a_build_to_wait_for() -> None:
    """🔴 ``None`` отдаёт и картина без статьи в Википедии. Без срока каждый тик долгого
    захода карточки шёл в сеть заново, а карточка висела недоехавшей: стенд `.104`,
    11-09-2026 - четыре фильма полки из пяти, по пять ``GET`` на карточку."""
    asked: list[str] = []

    def _silent(title: str, _series: bool, _timeout: float) -> list[Kin] | None:
        asked.append(title)
        return None

    lookup = RelatedLookup(franchise=_silent, offer=_passthrough, spawn=_sync, clock=lambda: 0.0)
    assert lookup.of("Maharaja Hostel", False) is None
    assert lookup.of("Maharaja Hostel", False) is None
    assert asked == ["Maharaja Hostel"]
    assert not lookup.waiting("Maharaja Hostel", False)


def test_a_healed_network_fills_the_shelf_that_silence_left_pending() -> None:
    """Сеть ожила - та же карточка достраивает полку без перезапуска и без часа ожидания."""
    answers: list[list[Kin] | None] = [None, [_ONE]]
    now = [0.0]

    def _franchise(_title: str, _series: bool, _timeout: float) -> list[Kin] | None:
        return answers.pop(0)

    lookup = RelatedLookup(
        franchise=_franchise, offer=_passthrough, spawn=_sync, clock=lambda: now[0]
    )
    assert lookup.of("Чужой", False) is None
    now[0] += SILENT + 1.0
    related = lookup.of("Чужой", False)
    assert related is not None and len(related) == 1


def test_a_failed_build_does_not_hold_the_title_pending_forever() -> None:
    """Упавший фон - не ответ и не вечное «ещё не готово»: имя отпускается, и следующий
    вопрос заводит новый добор, а не висит на погибшем."""
    spawned: list[str] = []
    now = [0.0]

    def _broken(_title: str, _series: bool, _timeout: float) -> list[Kin] | None:
        raise OSError("network down")

    def _counted(job: Callable[[], None]) -> None:
        spawned.append("x")
        job()

    lookup = RelatedLookup(
        franchise=_broken, offer=_passthrough, spawn=_counted, clock=lambda: now[0]
    )

    assert lookup.of("Чужой", False) is None
    assert not lookup.waiting("Чужой", False)
    now[0] += SILENT + 1.0
    assert lookup.of("Чужой", False) is None
    assert len(spawned) == 2, "погибший добор держит имя занятым - второй добор не завёлся"


def test_one_name_of_two_kinds_keeps_two_shelves_and_not_one() -> None:
    """🔴 Имя и род - оба ключ полки: у сериала и фильма одного имени полки РАЗНЫЕ.

    Род карточка берёт из разбора раздач и передаёт в паспорт, а статья фильма и статья
    сериала в Википедии разные. Общий ключ отдавал полку одного другому: замер
    10-09-2026 на стенде `.104` - открытая первой карточка `tv:чужой:2021` гасила
    «Чужого» 1979 года на час, а открытая первой карточка фильма приписывала сериалу
    шесть частей чужой франшизы.
    """

    def _by_kind(_title: str, series: bool, _timeout: float) -> list[Kin]:
        return [] if series else [_ONE, _TWO]

    for order in ((True, False), (False, True)):
        lookup = RelatedLookup(franchise=_by_kind, offer=_passthrough, spawn=_sync)
        sizes = {series: len(lookup.of("Чужой", series) or []) for series in order}
        assert sizes == {True: 0, False: 2}, f"полки перепутались, порядок {order}"


def test_the_cached_tiles_answer_the_next_ask_without_asking_wikidata_again() -> None:
    """Второй вопрос о той же картине не зовёт Wikidata заново - ответ уже в кэше."""
    asked: list[str] = []

    def _franchise(title: str, _series: bool, _timeout: float) -> list[Kin]:
        asked.append(title)
        return [_ONE]

    lookup = RelatedLookup(franchise=_franchise, offer=_passthrough, spawn=_sync)
    lookup.of("Гарри Поттер и философский камень", False)

    lookup.of("Гарри Поттер и философский камень", False)

    assert asked == ["Гарри Поттер и философский камень"]


def test_a_pending_build_is_not_started_twice_for_the_same_title() -> None:
    """Второй вопрос, пока фон ещё бежит, не заводит второй параллельный разбор."""
    spawned: list[Callable[[], None]] = []
    lookup = RelatedLookup(franchise=lambda *_a: [_ONE], offer=_passthrough, spawn=spawned.append)
    lookup.of("Гарри Поттер и философский камень", False)

    lookup.of("Гарри Поттер и философский камень", False)

    assert len(spawned) == 1


def test_the_poster_offer_decorates_tiles_the_same_way_as_the_shelves() -> None:
    """Обложка приходит тем же приговором, что и у полок - розыскное поле после него уходит."""

    def _offer(records: list[JsonValue]) -> list[JsonValue]:
        return [
            {**record, "poster": "abc123"} if isinstance(record, dict) else record
            for record in records
        ]

    lookup = RelatedLookup(franchise=lambda *_a: [_ONE], offer=_offer, spawn=_sync)

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is not None
    tile = related[0]
    assert isinstance(tile, dict)
    assert tile["poster"] == "abc123"
    assert "original" not in tile


def test_the_related_titles_are_warmed_before_the_tiles_are_drawn() -> None:
    """Соседняя серия берёт уже согретый круг, не ждёт обхода плиток в браузере."""
    warmed: list[list[str]] = []
    lookup = RelatedLookup(
        franchise=lambda *_a: [_ONE, _TWO], offer=_passthrough, warm=warmed.append, spawn=_sync
    )

    lookup.of("Гарри Поттер и философский камень", False)

    assert warmed == [["Гарри Поттер и философский камень"]]


def _passport(_title: str, _series: bool, _timeout: float) -> Origin:
    return Origin(title="Harry Potter and the Chamber of Secrets")


def test_the_related_tile_speaks_the_passports_latin_name_under_english(
    _english: None,
) -> None:
    """§8: под английским языком плитка родни говорит паспортом, а не записью Wikidata."""
    lookup = RelatedLookup(
        franchise=lambda *_a: [_ONE], offer=_passthrough, passport=_passport, spawn=_sync
    )

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is not None
    tile = related[0]
    assert isinstance(tile, dict)
    assert tile["title"] == "Гарри Поттер и Тайная комната"
    assert tile["shown"] == "Harry Potter and the Chamber of Secrets"


def test_the_related_tile_keeps_the_recorded_name_under_russian_even_with_a_passport(
    _russian_product: None,
) -> None:
    """Позитивный контроль: под русским языком найденный паспорт ничего не меняет
    и не звонит - незачем."""
    asked: list[str] = []

    def _watched(title: str, series: bool, timeout: float) -> Origin:
        asked.append(title)
        return _passport(title, series, timeout)

    lookup = RelatedLookup(
        franchise=lambda *_a: [_ONE], offer=_passthrough, passport=_watched, spawn=_sync
    )

    related = lookup.of("Гарри Поттер и философский камень", False)

    assert related is not None
    tile = related[0]
    assert isinstance(tile, dict)
    assert tile["title"] == "Гарри Поттер и Тайная комната"
    assert tile["shown"] == "Гарри Поттер и Тайная комната"
    assert asked == []
