"""Русское название, а раздачи подписаны латиницей: второй заход поиска.

Половина каталога подписана только на латинице («Psycho.1960.1080p»), и русский
запрос до неё не достаёт: индексер ищет по имени раздачи. Здесь проверяется, что
torrcast сам догадывается переспросить, откуда он берёт оригинальное название и
что на полной выдаче второго запроса не случается вовсе.

Отдельный набор - гейт добора: чужая картина под тем же русским именем не должна
проехать молча, даже если раздач от неё стало заметно больше.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import pytest

from tests.fakes.passport import FakePassport
from tests.fakes.prowlarr import FakeProwlarr
from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.prowlarr.merge import merge
from torrcast.domain.alt_query import alt_query
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.picture import Picture
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.thin_pool import THIN_POOL
from torrcast.domain.transliterate import transliterate
from torrcast.domain.unswap_layout import unswap_layout
from torrcast.usecases.choice.default_note import default_note
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.discover.search_circle import search_circle as circle
from torrcast.usecases.reinforce.same_picture import same_picture

GB = 1024**3


@pytest.fixture(autouse=True)
def _russian_titles(_russian_product: None) -> None:
    """Предмет модуля - русское название как русское: транслит, склонение, порядок слов."""


def _knows(passports: dict[str, Origin]) -> FakePassport:
    """Справка с готовыми паспортами: она же и записывает, о чём её спрашивали."""
    return FakePassport(passports)


def raw(
    name: str,
    number: int,
    seeders: int = 100,
    indexer: str = "Knaben",
    size: float = 8 * GB,
) -> RawResult:
    """Строка выдачи: hash различает раздачи, по нему же они и склеиваются."""
    return RawResult(
        title=name, info_hash=f"{number:040x}", size=int(size), seeders=seeders, indexer=indexer
    )


def ru(name: str) -> Release:
    return parse_release_name(name)


def test_transliterate_writes_russian_title_in_latin() -> None:
    assert transliterate("Брат") == "brat"
    assert transliterate("Ёлки") == "elki"
    assert transliterate("Щука") == "shchuka"
    assert transliterate("Иван Васильевич") == "ivan vasilevich"


def test_transliterate_keeps_latin_and_digits() -> None:
    assert transliterate("Матрица 2") == "matritsa 2"
    assert transliterate("The Matrix") == "the matrix"


def test_alt_query_takes_original_title_from_the_thin_results() -> None:
    """Оригинал из выдачи точнее транслита: «Психо» → Psycho, а не psikho."""
    thin = [ru("Психо / Psycho (1960) BDRip 1080p"), ru("Психо / Psycho (1960) DVDRip")]
    assert alt_query("психо", thin) == "Psycho"


def test_a_latin_query_prefers_the_references_original_over_the_native_name() -> None:
    """🔴 TC-399. Короткое обиходное имя латиницей добирается полным оригиналом справки.

    По «lain» справка назвала и оригинал (``Serial Experiments Lain``), и русское имя
    («Эксперименты Лэйн»). Добор русским именем проигрывает: русскоязычные индексеры
    отвечают дольше всех, и круг закрывается кворумом быстрых до их ответа - живая
    проба так и принесла ноль, тогда как под оригиналом картина лежит у быстрых.
    Совпадающий с запросом оригинал («cars» → ``Cars``) нового круга не даст - тогда
    берётся русское имя, как и раньше.
    """
    assert (
        alt_query("lain", [], known="Serial Experiments Lain", native="Эксперименты Лэйн")
        == "Serial Experiments Lain"
    )
    assert alt_query("cars", [], known="Cars", native="Тачки") == "Тачки"


def test_alt_query_prefers_the_most_common_original() -> None:
    pool = [
        ru("Сияние / The Shining (1980) BDRip 1080p"),
        ru("Сияние / The Shining (1980) DVDRip"),
        ru("Сияние / Shine (1996) DVDRip"),
    ]
    assert alt_query("сияние", pool) == "The Shining"


def test_alt_query_ignores_originals_of_other_pictures() -> None:
    """В выдаче по «психо» лежит и «Идентификация», её оригинал брать нельзя."""
    pool = [
        ru("Идентификация / Identity (2003) BDRip"),
        ru("Психо / Psycho (1960) DVDRip"),
    ]
    assert alt_query("психо", pool) == "Psycho"


def test_alt_query_falls_back_to_translit_when_nothing_was_found() -> None:
    """Выдачи нет вовсе - читать оригинал неоткуда, остаётся транслит."""
    assert alt_query("брат", []) == "brat"


def test_alt_query_does_not_transliterate_a_phrase_without_an_original() -> None:
    """Длинное имя другими буквами - заведомо пустой круг, а не другое имя картины."""
    hopeless = (
        "Американская фабрика",
        "13-я поправка",
        "Супер размер меня",
        "Колыма - родина нашего страха",
        "Двадцать шагов до славы",
        "Оазис: Суперзвуковой",
    )

    assert [alt_query(title, []) for title in hopeless] == [""] * len(hopeless)


def test_alt_query_is_empty_for_a_latin_request() -> None:
    """Спросили латиницей - добирать нечем, второго захода не бывает."""
    assert alt_query("psycho", [ru("Психо / Psycho (1960) DVDRip")]) == ""


def test_merge_keeps_each_torrent_once_and_holds_the_order() -> None:
    first, second = [raw("Психо", 1), raw("Психо", 2)], [raw("Psycho", 2), raw("Psycho", 3)]
    merged = merge(first, second)
    assert [r.title for r in merged] == ["Психо", "Психо", "Psycho"]


def test_merge_remembers_how_many_indexers_carried_the_torrent() -> None:
    """Склеили три зеркальные выдачи - раздача одна, но строк за ней три."""
    mirrors = [
        [raw("Психо / Psycho (1960) DVDRip", 1, indexer=name)]
        for name in ("Knaben", "RuTor", "Nyaa.si")
    ]
    merged = merge(*mirrors)
    assert [r.copies for r in merged] == [3]


def test_merge_does_not_count_the_same_indexer_twice() -> None:
    """Второй круг по другому имени приносит те же строки от тех же индексеров - каталог
    от этого не удваивается: считаем разные индексеры, а не сложенные круги.
    """
    ru_round = merge([raw("Психо / Psycho (1960) DVDRip", 1, indexer="Knaben")], [])
    latin_round = [raw("Psycho 1960 DVDRip", 1, indexer="Knaben")]
    assert [r.copies for r in merge(ru_round, latin_round)] == [1]


def _catalog(russian: int, latin: int, quality: str = "DVDRip") -> FakeProwlarr:
    """«Психо»: по-русски пара DVDRip'ов, на латинице - весь каталог в 1080p.

    ``quality`` - чем подписаны РУССКИЕ строки. Умолчание и есть беда: DVDRip мимо
    отбора, и такой пул негоден, сколько бы строк в нём ни было (TC-245). Полным и
    годным его делает ровно то, ради чего всё затевалось, - живой 1080p.
    """
    return FakeProwlarr(
        {
            "психо": [raw(f"Психо / Psycho (1960) {quality} {i}", i) for i in range(russian)],
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(latin)],
        }
    )


def search_circle(
    client: FakeProwlarr, query: str, about: Callable[..., Origin] | None = None
) -> tuple[Any, str]:
    """План поиска и всё, что он сказал вслух."""
    config = Config(tv="127.0.0.1", prowlarr_apikey="KEY")
    args = Args(query=query.split())
    out = io.StringIO()
    with Progress(out=out) as progress:
        found = circle(config, args, progress, indexer=client, passport=about)
        return found, out.getvalue()


def test_thin_russian_pool_is_topped_up_by_the_latin_title() -> None:
    """Два русских DVDRip'а - повод переспросить: рядом лежит сорок 1080p."""
    client = _catalog(russian=2, latin=40)
    plans, said = search_circle(client, "психо")

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 42
    assert "по-русски раздач 2 - добрал по «Psycho»: стало 42" in said


def test_full_russian_pool_is_not_searched_twice() -> None:
    """Счастливый путь не платит за чужую беду: полная и годная выдача - один запрос."""
    client = _catalog(russian=THIN_POOL, latin=40, quality="BDRip 1080p")
    plans, _said = search_circle(client, "психо")

    assert client.asked == ["психо"]
    assert len(plans[0].picture.releases) == THIN_POOL


def test_a_fat_but_sd_russian_pool_asks_the_original_too() -> None:
    """🔴 TC-245. Толщина пула про его годность не говорит ничего.

    Замер каталога: «Оранжевый хит сезона» приезжал 57 русскими строками без единого HD,
    отбор перебирал мертвецов и сдавался, а под ``Orange Is the New Black`` лежали 93 HD.
    Тощесть тут не срабатывала ни разу - строк-то много, - и второго захода не случалось.
    """
    client = _catalog(russian=THIN_POOL + 5, latin=40)
    plans, said = search_circle(client, "психо")

    assert client.asked == ["психо", "Psycho"], "HD ноль - это тоже повод спросить оригинал"
    assert len(plans[0].picture.releases) == THIN_POOL + 45
    assert f"по-русски раздач {THIN_POOL + 5} - добрал по «Psycho»" in said


def test_a_fat_but_dead_russian_pool_asks_the_original_too() -> None:
    """Вторая половина того же: HD в пуле есть, а сидов под ним нет.

    Порог живости тут тот же, которым меряется картина в меню
    (:data:`~torrcast.domain.rank_settings.ALIVE_SEEDERS`): под ним раздача не играет, и пул из
    таких строк негоден ровно так же, как пул из одного SD.
    """
    client = FakeProwlarr(
        {
            "психо": [
                raw(f"Психо / Psycho (1960) BDRip 1080p {i}", i, seeders=ALIVE_SEEDERS - 3)
                for i in range(THIN_POOL + 5)
            ],
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(40)],
        }
    )
    plans, said = search_circle(client, "психо")

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == THIN_POOL + 45
    assert "добрал по «Psycho»" in said


def test_a_fat_pool_of_living_old_rips_still_asks_the_original() -> None:
    """🔴 TC-262. Живое старьё в пуле - не повод отказаться от второго захода.

    Соблазн сузить повод до «негоден И мёртв» (раз старьё живо, вечер как-то состоится)
    замер тысячи запросов отверг: это сняло бы одну трату в 2.3 с вместе с ПЯТЬЮ
    вечерами, где живым в пуле было только старьё, а под оригиналом лежал живой 1080p, -
    «Конклав», «Реальная любовь», «Крёстный отец 2», «Шёпот сердца» и «Иван Васильевич
    меняет профессию». Цена самого повода при этом мала: 16 запросов из 1000 и 1.84 с по
    медиане (:func:`~torrcast.usecases.discover.worth_asking_original.worth_asking_original`).

    Пул тут ровно такой: DVDRip'ы названы кодеком, а значит ворота отбора проходят
    (:attr:`~torrcast.domain.release.Release.prime`), сидов под ними полно, - и всё равно
    спрашиваем оригинал. От соседнего теста отличается именно этим: там старьё до
    очереди не доезжает, здесь доезжает и играется.
    """
    sd = ru("Психо / Psycho (1960) DVDRip x264 0")
    assert sd.prime and sd.dated, "премиса: старьё, которое ворота отбора всё же проходит"

    client = _catalog(russian=THIN_POOL + 5, latin=40, quality="DVDRip x264")
    plans, said = search_circle(client, "психо")

    assert client.asked == ["психо", "Psycho"], "живое старьё - это не годный релиз"
    assert len(plans[0].picture.releases) == THIN_POOL + 45
    assert "добрал по «Psycho»" in said


def _mirror(count: int, *indexers: str, quality: str = "BDRip 1080p") -> list[RawResult]:
    """Одни и те же ``count`` раздач «Психо», принесённые каждым из индексеров.

    Так и выглядит живой круг: Knaben несёт то же, что nyaa и остальные, и после склейки
    по ``infoHash`` от трёх выдач остаётся одна.

    Раздачи годные нарочно: здесь мерится ТОЩЕСТЬ пула, и негодность (TC-245) в эту мерку
    лезть не должна - иначе тест проходил бы по другой причине, чем написано.
    """
    return merge(
        *[
            [raw(f"Психо / Psycho (1960) {quality} {i}", i, indexer=name) for i in range(count)]
            for name in indexers
        ]
    )


def test_a_mirrored_pool_is_not_mistaken_for_a_thin_one() -> None:
    """Шесть раздач от трёх зеркалящих индексеров - восемнадцать строк выдачи, и это не
    повод для второго круга: столько же строк отдавал и общий запрос, по которому мерился
    порог. Иначе цена поиска зависела бы от того, сколько индексеров дублируют друг друга.
    """
    client = FakeProwlarr(
        {
            "психо": _mirror(6, "Knaben", "RuTor", "Nyaa.si"),
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(40)],
        }
    )

    plans, _said = search_circle(client, "психо")

    assert client.asked == ["психо"], "зеркала склеились - но каталог от этого не обеднел"
    assert len(plans[0].picture.releases) == 6


def test_a_truly_poor_pool_still_asks_the_latin_title() -> None:
    """Те же шесть раздач, но их несёт один индексер: шесть строк - пул честно тощий,
    и второй круг по латинскому имени обязан случиться. Механизм не заглушён.
    """
    client = FakeProwlarr(
        {
            "психо": _mirror(6, "Knaben"),
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(40)],
        }
    )

    plans, said = search_circle(client, "психо")

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 46
    assert "добрал по «Psycho»" in said


def test_a_series_missing_the_wanted_season_is_topped_up_by_the_season_string() -> None:
    """Сезон-пак под оригинальным именем: «ангел» его не приносит, «Angel S01» - да.

    У западного сериала русский запрос отдаёт раздачи чужих сезонов (S03, S04), а пак
    первого сезона лежит под латинским «Angel [S01-05]», до которого «ангел» не достаёт.
    Прежде отбор упирался в «раздач с сезоном 1 нет»; теперь сезонная строка по оригиналу
    его добирает - а чужое одноимённое аниме («The Angel Next Door ... S01») в пул не
    попадает: у него другой оригинал, и фильтр добора его отсекает.
    """
    about = _knows({})  # справка молчит - оригинал берётся из выдачи (Angel)
    client = FakeProwlarr(
        {
            "ангел": [
                raw("Ангел / Angel [S03] (2001) WEB-DL 1080p", 1),
                raw("Ангел / Angel [S04] (2003) WEB-DL 1080p", 2),
            ],
            "angel s01": [
                raw("Ангел / Angel [S01-05] (1999) DVDRip | ТВ3", 3, seeders=0),
                raw("The Angel Next Door Spoils Me Rotten S01 1080p", 4),
            ],
        }
    )
    plans, said = search_circle(client, "ангел", about)

    assert "Angel S01" in client.asked, "сезонная строка по оригиналу спрошена"
    packs = [r for p in plans for r in p.picture.releases if r.covers(1)]
    assert packs, "сезон-пак первого сезона добрался в план"
    assert all(slugify(r.original or "") == "angel" for r in packs), "чужого аниме в пуле нет"
    assert phrase("reinforce.season_note", season=1, query="Angel S01") in said


def test_a_full_season_pool_skips_the_season_string_top_up() -> None:
    """Нужный сезон в выдаче есть - лишнего круга по сезонной строке не бывает."""
    about = _knows({})
    client = FakeProwlarr(
        {"ангел": [raw("Ангел / Angel [S01] (1999) WEB-DL 1080p", i) for i in range(3)]}
    )
    _plans, said = search_circle(client, "ангел", about)

    assert not any(a.startswith("Angel S") for a in client.asked), "сезон есть - добора нет"
    assert "добрал по" not in said


def test_a_guessed_origin_is_not_the_season_top_up_filter() -> None:
    """Догадка справки - не ключ фильтра сезонного добора.

    У вожака нет оригинала в имени раздач, а справка статьи про «незнакомку» не нашла -
    лишь признала похожей чужую (``The Stranger``). Такое имя, став ключом фильтра,
    пропускает раздачи ЧУЖОГО сериала: они сшиваются с вожаком по русскому имени, и
    человек молча получает «The Stranger» вместо «Незнакомки» - подмену мимо гейта
    TC-253. Поэтому догадка без второго признака добором не берётся: сезонная строка
    строится транслитом и, ничего не найдя, честно отказывает.
    """
    about = _knows(
        {"незнакомка": Origin(title="The Stranger", name="Незнакомые", guessed=True)},
    )
    client = FakeProwlarr(
        {
            "незнакомка": [
                raw(f"Незнакомка [S02] (2021) WEB-DL 1080p {i}", i) for i in range(THIN_POOL + 1)
            ],
            "the stranger s01": [
                raw("Незнакомка / The Stranger [S01] (2020) WEB-DL 1080p", 100),
                raw("The Stranger S01 1080p WEB-DL", 101),
            ],
        }
    )

    with pytest.raises(NotFoundError, match="раздач с сезоном 1 нет"):
        search_circle(client, "незнакомка s1e1", about)

    assert "The Stranger S01" not in client.asked, "сезонная строка по догадке не спрошена"


def test_a_guess_the_reference_confirms_still_tops_up_the_season() -> None:
    """Догадку, которую справка подтверждает сама, добор берёт: описка «сальтберн».

    Статья названа тем же словом, что спросили («Солтберн» - та же картина в другой
    транскрипции), и это ровно тот второй признак, с которым гейт добора верит имени
    со справки (:func:`torrcast.usecases.discover._second_language._second_language`). Сезонная
    строка по ``Saltburn`` законна и добирает пак, как и прежде.
    """
    about = _knows({"сальтберн": Origin(title="Saltburn", name="Солтберн", guessed=True)})
    client = FakeProwlarr(
        {
            "сальтберн": [
                raw(f"Сальтберн [S02] (2023) WEB-DL 1080p {i}", i) for i in range(THIN_POOL + 1)
            ],
            "saltburn s01": [
                raw(f"Сальтберн / Saltburn [S01] (2023) WEB-DL 1080p e0{i}", 100 + i)
                for i in range(1, 4)
            ],
        }
    )

    plans, said = search_circle(client, "сальтберн s1e1", about)

    assert "Saltburn S01" in client.asked, "сезонная строка по подтверждённой догадке спрошена"
    packs = [r for p in plans for r in p.picture.releases if r.covers(1)]
    assert packs, "сезон-пак первого сезона добрался в план"
    assert phrase("reinforce.season_note", season=1, query="Saltburn S01") in said


def test_nothing_found_in_russian_is_searched_by_translit() -> None:
    """Пустая выдача - тот же случай: читать оригинал неоткуда, идём транслитом."""
    client = FakeProwlarr({"brat": [raw(f"Brat.1997.BDRip.x264-{i}", i) for i in range(20)]})
    plans, _said = search_circle(client, "брат")

    assert client.asked == ["брат", "brat"]
    assert len(plans[0].picture.releases) == 20


class _SpentProwlarr(FakeProwlarr):
    """Тот же каталог, но первый круг уже съел цель почти всю (TC-386)."""

    def __init__(self, catalog: dict[str, list[RawResult]], spare: float) -> None:
        super().__init__(catalog)
        self._spent = spare
        #: Пол бюджета, с которым спрошен каждый круг: у добора он обязан быть целью.
        self.floors: list[float] = []

    def search(self, query: str, limit: int = 100) -> list[RawResult]:
        self.floors.append(self.cap_floor)
        return super().search(query, limit)

    def spare(self) -> float:
        return self._spent


def test_thin_pool_is_topped_up_even_when_the_goal_is_spent() -> None:
    """🔴 TC-386. Цель съедена первым кругом - добор по второму имени не отменяется.

    Отмена стоила картины: живой замер TC-372 - «тачки» при медленном Knaben (7.0 с
    вместо 0.5) теряли пул с 28 раздач до 4-5 и кончались кодом 1. По лестнице целей
    «не включилось» сильнее «дольше 10 секунд»: круг добора идёт с полом в целую цель,
    человек читает про превышение строкой, а после захода пол возвращён обычному.
    """
    from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL

    client = _SpentProwlarr(
        {
            "психо": [raw(f"Психо / Psycho (1960) DVDRip {i}", i) for i in range(2)],
            "psycho": [raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(40)],
        },
        spare=0.3,
    )
    plans, said = search_circle(client, "психо")

    assert client.asked == ["психо", "Psycho"], "добор съеденной целью не отменяется"
    assert len(plans[0].picture.releases) == 42
    assert "всё равно делаю" in said, "превышение цели объявлено вслух"
    assert "не делаю" not in said
    assert client.floors == [CIRCLE_SHARE, GOAL], "круг добора спрошен с полом в целую цель"
    assert client.cap_floor == CIRCLE_SHARE, "после добора пол возвращён обычному"


def test_empty_russian_answer_is_searched_even_when_the_goal_is_spent() -> None:
    """🔴 TC-386. Русская выдача пуста и цель съедена - добор делается и тут: без него
    не тощий пул, а честный отказ «ничего не нашлось» при живой картине в каталоге."""
    client = _SpentProwlarr(
        {"brat": [raw(f"Brat.1997.BDRip.x264-{i}", i) for i in range(20)]},
        spare=0.3,
    )
    plans, said = search_circle(client, "брат")

    assert client.asked == ["брат", "brat"], "и безнадёжный путь не отменяется бюджетом"
    assert len(plans[0].picture.releases) == 20
    assert "всё равно делаю" in said


def test_a_missing_old_namesake_is_searched_by_original_and_year() -> None:
    """Свежая тёзка не прячет первую картину за широким запросом без года."""
    client = FakeProwlarr(
        {
            "брат": [
                raw("Брат / Brat (2025) WEB-DL 1080p", 1),
                raw("Брат 2 / Brat 2 (2000) BDRip 1080p", 2),
            ],
            "брат 1997": [raw("Брат / Brat (1997) BDRip 1080p", 3)],
        }
    )
    about = _knows({"брат": Origin(title="Brat", year=1997, name="Брат")})

    plans, _said = search_circle(client, "брат", about)

    assert client.asked == ["брат", "брат 1997"]
    assert [plan.picture.year for plan in plans] == [1997, 2000, 2025]


def test_second_search_that_found_nothing_leaves_the_first_result_alone() -> None:
    """Добор - не обещание: не нашлось ничего нового, играем то, что было, и молчим."""
    client = _catalog(russian=3, latin=0)
    plans, said = search_circle(client, "психо")

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 3
    assert "добрал" not in said


def test_nothing_anywhere_is_still_an_honest_not_found() -> None:
    client = FakeProwlarr({})
    with pytest.raises(NotFoundError, match="ничего не нашлось"):
        search_circle(client, "нетакогофильма")


def test_results_full_of_strangers_are_reported_as_nothing_found() -> None:
    """Выдача есть, а картины в ней нет - это «не нашлось», а не разговор про франшизу.

    «Дети мужчин» в каталоге зовутся «Дитя человеческое», и по набранному имени приезжают
    только однофамильцы. Прежде такому человеку отвечали «такой картины во франшизе нет»,
    и он шёл проверять номер части у фильма, которого поиск вообще не видел.
    """
    client = FakeProwlarr(
        {"дети мужчин": [raw(f"Мужчины, женщины и дети (2014) BDRip {i}", i) for i in range(20)]}
    )

    with pytest.raises(NotFoundError) as caught:
        search_circle(client, "дети мужчин")

    assert "ничего не нашлось" in str(caught.value)
    assert "франшиз" not in str(caught.value)


def test_a_part_that_the_franchise_does_not_have_is_named_as_such() -> None:
    """А вот когда франшиза нашлась, а части в ней нет - так и говорим, с числом частей."""
    client = FakeProwlarr(
        {"матрица": [raw(f"Матрица / The Matrix (1999) BDRip {i}", i) for i in range(20)]}
    )

    with pytest.raises(NotFoundError) as caught:
        search_circle(client, "матрица 5")

    assert "картин во франшизе 1, номера 5 нет" in str(caught.value)
    assert client.asked[:2] == ["матрица", "матрица 5"], "всей строкой спросили вместо отказа"


def test_a_number_that_belongs_to_the_title_is_searched_whole() -> None:
    """🔴 TC-296. «бен 10» - целое имя, а не десятая часть франшизы «бен».

    Живой каталог: по строке «бен» приезжает «Бен» 1972 года и три десятка однофамильцев,
    а семи картин линейки «Бен 10» нет ВООБЩЕ НИ ОДНОЙ - их отдаёт только та же строка
    целиком. Человек читал «картин во франшизе 1, номера 10 нет» при живом сериале.
    """
    client = FakeProwlarr(
        {
            "бен": [raw(f"Бен / Ben (1972) BDRip {i}", i) for i in range(20)],
            "бен 10": [
                raw(f"Бен 10 / Ben 10 (2005) WEB-DL 1080p s01e0{i}", 100 + i) for i in range(1, 5)
            ],
        }
    )

    plans, said = search_circle(client, "бен 10")

    assert client.asked[:2] == ["бен", "бен 10"]
    assert [plan.picture.title for plan in plans] == ["Бен 10"]
    assert "искал «бен 10» целиком" in said


def test_a_number_at_a_series_name_asks_for_that_season() -> None:
    """🔴 TC-363. «человек-бензопила 2» - это второй сезон, а не вторая часть франшизы.

    Под именем сериала лежит и полный метр к нему, раздач у фильма больше, - и номер,
    отсчитанный по хронологии, отвечал фильмом. Теперь номер уходит в сезонную машинерию
    целиком: сезон спрашивается у раздач, добирается сезонной строкой по оригиналу и, если
    его нет, кончается честным отказом. Прочтение при этом названо вслух.
    """
    client = FakeProwlarr(
        {
            "человек-бензопила": [
                raw("Человек-бензопила / Chainsaw Man [S01] (2022) BDRip 1080p | D", 1),
                raw(
                    "Человек-бензопила. Фильм: История Резе / Chainsaw Man Movie: Reze-hen "
                    "(2025) WEB-DL 1080p | D",
                    2,
                ),
            ]
        }
    )

    with pytest.raises(NotFoundError) as caught:
        search_circle(client, "человек-бензопила 2")

    assert "раздач с сезоном 2 нет" in str(caught.value)
    plans, said = search_circle(client, "человек-бензопила 1")
    assert [(plan.picture.title, plan.picture.kind) for plan in plans] == [
        ("Человек-бензопила", "tv")
    ]
    assert "номер 1 читаю сезоном, а не частью" in said


def test_the_whole_string_is_not_asked_when_the_part_is_found() -> None:
    """Счастливый путь франшизы за это не платит: «тачки 2» находятся первым же кругом."""
    client = FakeProwlarr(
        {
            "тачки": [raw(f"Тачки / Cars (2006) BDRip {i}", i) for i in range(20)]
            + [raw(f"Тачки 2 / Cars 2 (2011) BDRip {i}", 100 + i) for i in range(20)]
        }
    )

    plans, _said = search_circle(client, "тачки 2")

    assert client.asked == ["тачки"]
    assert [plan.picture.year for plan in plans] == [2011]


def test_the_titled_number_reaches_the_season_top_up_whole() -> None:
    """🔴 TC-321. «бен 10 s2e1»: добор сезона спрашивает всю строку, а не обрубок «бен».

    Каталог уже ответил, что цифра - часть названия (TC-296), и добор вторым языком это
    знает. Сезонный добор строку делил ЗАНОВО, и в справку уезжал обрубок «бен» - тот,
    про который она отвечает «Бен-Гур». Справка по целому имени знает ``Ben 10``, и
    сезонная строка строится по ней.
    """
    about = _knows({"бен 10": Origin(title="Ben 10")})
    client = FakeProwlarr(
        {
            "бен": [raw(f"Бен / Ben (1972) BDRip {i}", i) for i in range(20)],
            "бен 10": [
                raw(f"Бен 10 (2005) WEB-DL 1080p s01e{i:02d}", 100 + i)
                for i in range(1, THIN_POOL + 1)
            ],
            "ben 10 s02": [
                raw(f"Бен 10 / Ben 10 (2005) WEB-DL 1080p s02e0{i}", 200 + i) for i in range(1, 5)
            ],
        }
    )

    plans, said = search_circle(client, "бен 10 s2e1", about)

    assert about.asked, "добор до справки дошёл"
    assert set(about.asked) == {"бен 10"}, "справку спросили целой строкой, а не обрубком «бен»"
    assert "Ben 10 S02" in client.asked
    assert phrase("reinforce.season_note", season=2, query="Ben 10 S02") in said
    assert plans


def test_the_part_number_picks_inside_the_named_franchise() -> None:
    """«гарри поттер дары смерти 2» - это часть 2011 года, и добора ей не нужно.

    Номер уходит из строки поиска (спрашиваем «гарри поттер дары смерти») и работает
    выбором картины. Пока запрос без союза «и» не совпадал с каталогом, пул выходил
    пустым, поиск шёл на второй круг по франшизе целиком и привозил антологию.
    """
    client = FakeProwlarr(
        {
            "гарри поттер дары смерти": [
                raw(f"Гарри Поттер и Дары смерти: Часть 1 (2010) BDRip {i}", i) for i in range(20)
            ]
            + [
                raw(f"Гарри Поттер и Дары Смерти: Часть II (2011) BDRip {i}", 100 + i)
                for i in range(20)
            ]
        }
    )

    plans, _said = search_circle(client, "гарри поттер дары смерти 2")

    assert client.asked == ["гарри поттер дары смерти"]
    assert [p.picture.year for p in plans] == [2011]


def test_a_named_part_is_not_thrown_away_by_the_year_of_the_first_one() -> None:
    """«тачки 2» - это 2011 год, и справка про «Тачки» 2006-го его не отменяет.

    Справку зовут по имени франшизы, и год она называет первой картины. Гейт добора читал
    это расхождение как подмену и выбрасывал честную выдачу: на живом каталоге «тачки 2»
    не находились вовсе.
    """
    client = FakeProwlarr(
        {"тачки": [raw(f"Тачки 2 / Cars 2 (2011) BDRip {i}", i) for i in range(3)]}
    )
    about = _knows({"тачки": Origin(title="Cars", year=2006)})

    plans, said = search_circle(client, "тачки 2", about)

    assert [p.picture.year for p in plans] == [2011]
    prefix = phrase("reinforce.year_mismatch", found_year="FY-MARK", about_year="AY-MARK").split(
        "FY-MARK"
    )[0]
    assert prefix not in said


def test_a_year_that_disagrees_without_a_part_number_is_named_but_not_taken_away() -> None:
    """🔴 TC-248. Без номера части год справки говорит своё слово, но выдачу не отнимает.

    Спросили «тачки», справка знает первую картину 2006 года, а в каталоге под этим именем
    лежит только вторая, 2011-го. Прежде гейт выбрасывал её вместе со всей выдачей и
    отвечал «ничего не нашлось» - при живых раздачах в руках. Расхождение печатается
    строкой, картину с её годом человек видит в меню и решает сам.
    """
    client = FakeProwlarr(
        {"тачки": [raw(f"Тачки 2 / Cars 2 (2011) BDRip {i}", i) for i in range(3)]}
    )
    about = _knows({"тачки": Origin(title="Cars", year=2006)})

    plans, said = search_circle(client, "тачки", about)

    assert [p.picture.year for p in plans] == [2011]
    line = phrase("reinforce.year_mismatch", found_year=2011, about_year=2006)
    assert line in said


def test_other_word_order_is_found_and_said_out_loud() -> None:
    """«бульвар сансет» играет «Сансет бульвар» - и об этом сказано вслух."""
    client = FakeProwlarr(
        {
            "бульвар сансет": [
                raw(f"Сансет бульвар / Sunset Blvd (1950) BDRip {i}", i) for i in range(20)
            ]
        }
    )

    plans, said = search_circle(client, "бульвар сансет")

    assert [p.picture.title for p in plans] == ["Сансет бульвар"]
    assert "«бульвар сансет» - в каталоге это «Сансет бульвар»" in said


def _namesakes() -> FakeProwlarr:
    """«Восхождение»: фильм Шепитько 1977 года и китайский 2019-го под тем же именем.

    Оригинал ``The Climbers`` лежит прямо в русской выдаче - именно им добор и уезжал
    в чужое кино, принося два десятка раздач с дорожкой ``und``.
    """
    return FakeProwlarr(
        {
            "восхождение": [raw(f"Восхождение (1977) DVDRip {i}", i) for i in range(4)]
            + [raw(f"Восхождение / The Climbers (2019) WEB-DL {i}", 50 + i) for i in range(2)],
            "the climbers": [
                raw(f"The.Climbers.2019.1080p.WEB-DL.x264-{i}", 100 + i) for i in range(20)
            ],
        }
    )


def _unglued() -> FakeProwlarr:
    """Две половины одной картины, которые нечем сшить: русская и латинская.

    Дословная форма живого случая: русские раздачи «Синего экзорциста» несут оригинал,
    а латинские - только своё имя, без года и без русского названия. Кластер оставляет
    их разными картинами, и привязка к картине по русскому запросу латинскую половину
    не видит.
    """
    return FakeProwlarr(
        {
            "синий экзорцист": [
                raw(f"Синий экзорцист / Ao no Exorcist (2011) BDRip {i}", i, seeders=1)
                for i in range(3)
            ],
            "blue exorcist": [
                raw(f"Blue Exorcist S01E{i:02d} 1080p WEB-DL", 100 + i, seeders=33)
                for i in range(1, 26)
            ],
        }
    )


def test_the_top_up_is_not_lost_on_the_binding_to_a_picture() -> None:
    """🔴 Добор привёз картину под её латинским именем - и она обязана доехать до очереди.

    Прежде она пропадала целиком: pick_franchise по русскому запросу латинскую половину
    не находит, добор выходил «пустым», и человек оставался с тремя мёртвыми раздачами
    при двадцати пяти живых в той же выдаче.
    """
    client = _unglued()
    about = _knows({"синий экзорцист": Origin(title="Blue Exorcist", year=2009)})
    plans, said = search_circle(client, "синий экзорцист", about)

    assert client.asked == ["синий экзорцист", "Blue Exorcist"]
    assert {p.picture.title for p in plans} == {"Синий экзорцист", "Blue Exorcist"}
    assert max(len(p.picture.releases) for p in plans) == 25
    assert "добрал по «Blue Exorcist»" in said


def test_the_reference_year_of_a_whole_franchise_does_not_kill_the_top_up() -> None:
    """Справка о сериале называет год ПЕРВОГО сезона, а картины в каталоге - свои.

    Спорить тут не о чем: у латинских раздач года нет вовсе, и разводить ими нечего.
    Раньше это расхождение (2009 у справки против 2011 в каталоге) читалось как подмена.
    """
    client = _unglued()
    about = _knows({"синий экзорцист": Origin(title="Blue Exorcist", year=1066)})
    _plans, said = search_circle(client, "синий экзорцист", about)

    assert "приехала другая картина" not in said


def test_a_namesake_under_the_reference_name_is_still_refused() -> None:
    """🔴 Ослабление точечное: имя из справки ручается за картину, но не против ГОДА.

    Справка знает «Восхождение» Шепитько как ``The Ascent`` 1977 года, а в каталоге под
    этим именем лежит чужой фильм 2019-го на двадцать раздач. Раздач больше - картина
    другая, и подмешивать её к найденному нельзя.
    """
    client = FakeProwlarr(
        {
            "восхождение": [raw(f"Восхождение (1977) DVDRip {i}", i) for i in range(4)],
            "the ascent": [
                raw(f"The Ascent (2019) WEB-DL {i}", 100 + i, seeders=80) for i in range(20)
            ],
        }
    )
    about = _knows({"восхождение": Origin(title="The Ascent", year=1977)})
    plans, said = search_circle(client, "восхождение", about)

    assert client.asked == ["восхождение", "The Ascent"]
    assert [p.picture.year for p in plans] == [1977]
    assert max(len(p.picture.releases) for p in plans) == 4
    assert "добрал" not in said


def test_a_subtitle_query_needs_no_second_round() -> None:
    """🔴 «Кольца власти» - подзаголовок сериала, и картина находится с первого круга.

    Прежде запрос не привязывался ни к одной картине, пустой пул звал добор, тот
    приносил по оригиналу всю чужую франшизу - и гейт честно её отбраковывал вместе с
    русской выдачей. Человек читал «ничего не нашлось» при 20 живых раздачах.
    """
    client = FakeProwlarr(
        {
            "кольца власти": [
                raw(
                    "Властелин колец: Кольца власти / The Lord of the Rings: "
                    f"The Rings of Power (2022) WEB-DL 1080p {i}",
                    i,
                    seeders=91,
                )
                for i in range(20)
            ]
        }
    )
    about = _knows({})
    plans, said = search_circle(client, "кольца власти", about)

    assert client.asked == ["кольца власти"], "лишнего круга по индексерам не нужно"
    assert about.asked == [], "справку тоже не тревожим: пул полон"
    assert [p.picture.title for p in plans] == ["Властелин колец: Кольца власти"]
    assert len(plans[0].picture.releases) == 20
    assert "ничего не нашлось" not in said


def test_a_dead_namesake_no_longer_swallows_a_subtitle_query() -> None:
    """🔴 TC-246. «Космическая одиссея»: вердикт «рой мёртв» по одной чужой раздаче.

    Под этим именем в каталоге лежит картина 1987 года с единственной мёртвой раздачей, и
    запрос доставался ей целиком - при 21 строке в пуле. Классика 1968 года подписана
    ``2001: Космическая одиссея``, её ключ - ``2001``, и до меню она не доезжала вовсе.

    Теперь в меню обе, дефолт стоит на живой, и человек читает обе стороны выбора.
    """
    client = FakeProwlarr(
        {
            "космическая одиссея": [
                raw(
                    f"2001: Космическая одиссея / 2001: A Space Odyssey (1968) BDRip 1080p {i}",
                    i,
                    seeders=49,
                )
                for i in range(20)
            ]
            + [raw("Космическая одиссея (1987) VHSRip", 90, seeders=0)]
        }
    )
    plans, said = search_circle(client, "космическая одиссея")

    assert [p.picture.year for p in plans] == [1987, 1968], "в меню обе картины"
    assert first_alive(plans) == 2, "дефолт - живая, а не мёртвый огрызок"
    assert "«космическая одиссея» - в каталоге это «2001: Космическая одиссея»" in said
    note = default_note(plans, "космическая одиссея")
    assert note == phrase(
        "choice.note_instead_asked_why",
        asked="космическая одиссея",
        mine="2001: Космическая одиссея (1968)",
        other="Космическая одиссея (1987)",
        why=phrase("choice.why_nothing_playable"),
    )


def test_a_thin_subtitle_pool_is_never_zeroed_by_the_gate() -> None:
    """Пул тощий, добор привёз чужую франшизу - гейт её не берёт, но и своё не выбрасывает."""
    client = FakeProwlarr(
        {
            "кольца власти": [
                raw(
                    "Властелин колец: Кольца власти / The Lord of the Rings: "
                    f"The Rings of Power (2022) WEB-DL 1080p {i}",
                    i,
                    seeders=91,
                )
                for i in range(3)
            ],
            "the lord of the rings": [
                raw(f"The.Lord.of.the.Rings.The.War.of.the.Rohirrim.2024.1080p-{i}", 100 + i)
                for i in range(40)
            ],
        }
    )
    about = _knows({})
    plans, said = search_circle(client, "кольца власти", about)

    assert client.asked == ["кольца власти", "The Lord of the Rings"]
    assert [p.picture.title for p in plans] == ["Властелин колец: Кольца власти"]
    assert len(plans[0].picture.releases) == 3, "чужая франшиза к картине не подмешана"
    assert "добрал" not in said


def test_top_up_that_brings_a_namesake_picture_is_refused() -> None:
    """🔴 Раздач стало больше - но это раздачи другого фильма. Добор отменяется."""
    client = _namesakes()
    plans, said = search_circle(client, "восхождение")

    assert client.asked == ["восхождение", "The Climbers"]
    assert [p.picture.year for p in plans] == [1977, 2019]
    assert max(len(p.picture.releases) for p in plans) == 4
    assert "добрал" not in said
    assert "приехала другая картина" in said


def test_the_reference_year_never_takes_away_what_the_russian_query_found() -> None:
    """🔴 TC-248. «Крестьяне» и «Восхождение» держатся ОДНОВРЕМЕННО, одним тестом.

    У гейта года остаётся право не ДОБАВИТЬ своё и нет права ОТНЯТЬ найденное.

    «Крестьяне»: справка знает картину 1935 года, а каталог под этим именем несёт 2023-й
    живым BDRip 1080p. Прежде гейт выбрасывал его вместе с выдачей и отвечал «ничего не
    нашлось» - честный отказ при существующем кино, то есть брак. Теперь расхождение
    сказано строкой, а картина осталась: слово справки против слова каталога решает
    человек, он видит в меню и имя, и год.

    «Восхождение»: настоящую подмену тот же гейт ловит как ловил - чужой ``The Climbers``
    2019 года к выдаче Шепитько не подмешивается, потому что там его именно ДОБАВЛЯЮТ.
    """
    peasants = FakeProwlarr(
        {
            "крестьяне": [
                raw(f"Крестьяне / Chlopi (2023) BDRip 1080p {i}", i, seeders=44) for i in range(6)
            ]
        }
    )
    about = _knows({"крестьяне": Origin(year=1935)})

    plans, said = search_circle(peasants, "крестьяне", about)

    assert [p.picture.title for p in plans] == ["Крестьяне"]
    assert len(plans[0].picture.releases) == 6, "живой 1080p остался в руках"
    assert "ничего не нашлось" not in said
    line = phrase("reinforce.year_mismatch", found_year=2023, about_year=1935)
    assert line in said

    ascent, told = search_circle(_namesakes(), "восхождение", about)

    assert max(len(p.picture.releases) for p in ascent) == 4, "чужая картина не подмешана"
    assert "добрал" not in told
    assert "приехала другая картина" in told


def test_the_reference_year_outweighs_the_pool_in_the_gate() -> None:
    """Справка знает год картины - и он же отвергает однофамильца, кто бы ни был крупнее."""
    client = _namesakes()
    about = _knows({"восхождение": Origin(year=1977)})
    plans, said = search_circle(client, "восхождение", about)

    assert about.asked == ["восхождение"]
    assert max(len(p.picture.releases) for p in plans) == 4
    assert "добрал" not in said


def test_original_title_comes_from_the_reference_when_the_pool_has_none() -> None:
    """Оригинала в выдаче нет, транслит уходит в пустоту - выручает справка.

    ``кингсман секретная служба`` → ``kingsman sekretnaya sluzhba`` не находит ничего, и
    прежний добор на этом заканчивался. Справка знает имя картины - по нему и находится.
    """
    client = FakeProwlarr(
        {
            "кингсман секретная служба": [
                raw(f"Кингсман Секретная служба (2014) TS {i}", i) for i in range(2)
            ],
            "kingsman": [
                raw(
                    f"Кингсман: Секретная служба / Kingsman: The Secret Service (2014) BDRip {i}",
                    100 + i,
                )
                for i in range(30)
            ],
        }
    )
    about = _knows({"кингсман секретная служба": Origin(title="Kingsman", year=2014)})
    plans, said = search_circle(client, "кингсман секретная служба", about)

    assert about.asked == ["кингсман секретная служба"]
    assert client.asked == ["кингсман секретная служба", "Kingsman"]
    assert max(len(p.picture.releases) for p in plans) == 32
    assert "добрал по «Kingsman»" in said


def test_a_silent_reference_leaves_the_old_path_alone() -> None:
    """Сети нет - справка пуста, и добор идёт прежним путём: оригинал из выдачи.

    Молчание под типом вожака переспрашивается без типа (TC-399) - и тоже молчит,
    поэтому справку тут слышно дважды, а путь добора от этого не меняется.
    """
    client = _catalog(russian=2, latin=40)
    about = _knows({})
    plans, said = search_circle(client, "психо", about)

    assert about.asked == ["психо", "психо"], "под типом молчит - переспрос без типа, тоже мимо"
    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 42
    assert "добрал по «Psycho»" in said


def test_a_silent_answer_under_the_leads_kind_is_reasked_without_it() -> None:
    """🔴 TC-399. Тип, подсказанный мусорным вожаком тощего пула, не хоронит картину.

    По запросу «lain» приехала одна строка - самиздатовский журнал «lainzine 1-5», и
    его тип («не сериал») отправлял справку в молчание: статьи о фильме «Lain» нет,
    есть статья о СЕРИАЛЕ «Serial Experiments Lain». Молчание под типом
    переспрашивается без него - справка спрашивает обе статьи разом и верит лишь
    согласию, - и картина добирается полным оригиналом из её паспорта: русское имя
    тут проигрывает, круг добора по нему закрывается кворумом быстрых индексеров до
    ответа русскоязычных, а под оригиналом картина лежит у быстрых. Журнал при этом
    остаётся как был.
    """
    client = FakeProwlarr(
        {
            "lain": [raw("lainzine 1-5 (pdf)", 1, seeders=5)],
            "serial experiments lain": [
                raw(f"Serial Experiments Lain [S01] (1998) BDRip 1080p-{i}", 100 + i, seeders=50)
                for i in range(3)
            ],
        }
    )
    asked: list[tuple[str, bool | None]] = []

    def about(title: str, series: bool | None = False, budget: float = 0.0) -> Origin:
        asked.append((title, series))
        if series is None:  # без типа справка знает: это сериал «Serial Experiments Lain»
            return Origin(title="Serial Experiments Lain", name="Эксперименты Лэйн")
        return Origin()  # под типом «фильм», который назвал журнал, - молчание

    plans, said = search_circle(client, "lain", about)

    assert asked == [("lain", False), ("lain", None)], "молчание под типом - переспрос без него"
    assert client.asked == ["lain", "Serial Experiments Lain"]
    titles = [p.picture.title for p in plans]
    assert "Serial Experiments Lain" in titles, "картина добралась оригиналом из паспорта"
    assert "lainzine 1-5" in titles, "найденное первым запросом не отнимается"
    assert "добрал по «Serial Experiments Lain»" in said


def test_the_full_pool_asks_neither_the_indexers_nor_the_reference() -> None:
    """Счастливый путь не платит ни за второй круг по индексерам, ни за справку."""
    client = _catalog(russian=THIN_POOL, latin=40, quality="BDRip 1080p")
    about = _knows({"психо": Origin(title="Psycho", year=1960)})
    plans, _said = search_circle(client, "психо", about)

    assert client.asked == ["психо"]
    assert about.asked == []
    assert len(plans[0].picture.releases) == THIN_POOL


def test_an_unproven_original_is_not_trusted_on_an_empty_result() -> None:
    """Сверять не с чем: до добора картины не было, справка молчит.

    Транслит - это сами слова запроса, ему веры хватает. А вот оригиналу, вычитанному у
    чужой раздачи, - нет: «не нашлось» честнее наугад взятого однофамильца.
    """
    came = Picture(title="Незнакомцы", year=2008, releases=[])

    assert same_picture(None, came, Origin(), proven=True)
    assert not same_picture(None, came, Origin(), proven=False)


def test_the_reference_year_decides_who_is_who() -> None:
    """Год справки сильнее всего: и подтверждает картину, и отвергает однофамильца."""
    ours = Picture(title="Восхождение", year=1977, releases=[])
    theirs = Picture(title="Восхождение", year=2019, releases=[])

    assert same_picture(ours, theirs, Origin(year=2019), proven=False)
    assert not same_picture(ours, theirs, Origin(year=1976), proven=True)
    # Производство и прокат расходятся на год - это не подмена.
    assert same_picture(ours, ours, Origin(year=1976), proven=False)


def test_a_remake_with_the_same_original_is_not_a_substitution() -> None:
    """Ремейк с тем же оригиналом - та же картина, хоть годы и врозь.

    Справка знает «Fruits Basket» 2006, а у индексеров ремейк 2019: оригинал один и тот
    же, значит это добор той же вещи, а не подмена. А вот чужой оригинал год по-прежнему
    разводит - дыру для настоящих подмен совпадение русского имени не открывает.
    """
    remake = Picture(title="Корзинка фруктов", year=2019, original="Fruits Basket", releases=[])
    about = Origin(title="Fruits Basket", year=2006, name="Корзинка фруктов")
    assert same_picture(None, remake, about, proven=True)

    # «Восхождение» Шепитько (The Ascent) против китайского (The Climbers) - разные оригиналы.
    alien = Picture(title="Восхождение", year=2019, original="The Climbers", releases=[])
    ascent = Origin(title="The Ascent", year=1976, name="Восхождение")
    assert not same_picture(None, alien, ascent, proven=True)


def test_the_gate_keeps_a_series_without_a_year() -> None:
    """Годов не назвал никто (обычное дело у сериалов) - гейт сверяет франшизу и пропускает."""
    client = FakeProwlarr(
        {
            "дедвуд": [raw(f"Дедвуд / Deadwood S01E0{i} WEB-DL", i) for i in range(1, 5)],
            "deadwood": [
                raw(f"Deadwood.S01E{i:02d}.1080p.WEB-DL.x264", 100 + i) for i in range(1, 16)
            ],
        }
    )
    plans, said = search_circle(client, "дедвуд")

    assert client.asked == ["дедвуд", "Deadwood"]
    assert len(plans[0].picture.releases) == 19
    assert "добрал по «Deadwood»: стало 19" in said


def test_an_empty_result_asks_the_reference_by_the_query_itself() -> None:
    """🔴 Русская выдача пуста - оригинал брать неоткуда, кроме справки.

    Прежде на пустой выдаче оставался только транслит («Уэнсдей» → ``uensdey``), а он
    не находит ничего: раздачи подписаны ``Wednesday``. Справку спрашиваем по САМОМУ
    запросу - она отвечает про ту картину, которую спросили, а не про ту, что попала в
    выдачу (её нет вовсе).
    """
    client = FakeProwlarr(
        {"wednesday": [raw(f"Wednesday.S01E{i:02d}.1080p.NF.WEB-DL", i) for i in range(1, 9)]}
    )
    about = _knows({"уэнсдей": Origin(title="Wednesday")})

    plans, said = search_circle(client, "уэнсдей", about)

    assert about.asked == ["уэнсдей"]
    assert client.asked == ["уэнсдей", "Wednesday"]
    assert len(plans[0].picture.releases) == 8
    assert "добрал по «Wednesday»: стало 8" in said


def test_a_silent_reference_on_an_empty_result_still_goes_by_translit() -> None:
    """Сети нет - справка пуста, и остаётся ровно то, что было: транслит запроса."""
    client = FakeProwlarr({"brat": [raw(f"Brat.1997.BDRip.x264-{i}", i) for i in range(20)]})
    about = _knows({})

    plans, _said = search_circle(client, "брат", about)

    assert about.asked == ["брат"]
    assert client.asked == ["брат", "brat"]
    assert len(plans[0].picture.releases) == 20


def _refused(client: FakeProwlarr, query: str, about: Callable[..., Origin] | None = None) -> str:
    """Поиск, кончившийся отказом: всё, что при этом было сказано вслух."""
    config = Config(tv="127.0.0.1", prowlarr_apikey="KEY")
    out = io.StringIO()
    with Progress(out=out) as progress, pytest.raises(NotFoundError):
        circle(config, Args(query=query.split()), progress, indexer=client, passport=about)
    return out.getvalue()


def test_a_name_the_reference_only_guessed_does_not_bring_a_stranger() -> None:
    """🔴 TC-253. Русская выдача пуста, и справка знает имя лишь по сходству - не верим.

    Живая проба: статьи «Все мы незнакомцы» в русской Википедии нет вовсе, и справка
    находит по сходству имён «Все мы убийцы» - французскую картину 1952 года. На пустой
    выдаче сверять добор не с чем (:func:`~torrcast.usecases.reinforce.same_picture.same_picture` с
    ``before=None`` решала по одному происхождению имени), и чужое кино доезжало под знакомым именем
    - худший вид брака по спеке. Теперь справка обязана назвать ту же картину тем же именем; назвала
    другим - за её именем к индексерам не идём вовсе.
    """
    client = FakeProwlarr(
        {
            "nous sommes tous des assassins": [
                raw(f"Nous.sommes.tous.des.assassins.1952.DVDRip.x264-{i}", i) for i in range(20)
            ]
        }
    )
    about = _knows(
        {
            "все мы незнакомцы": Origin(
                title="Nous sommes tous des assassins", name="Все мы убийцы", guessed=True
            )
        },
    )

    said = _refused(client, "все мы незнакомцы", about)

    assert "nous sommes tous des assassins" not in client.asked, (
        "за чужой картиной не ходят даже разок"
    )
    assert all(word in "все мы незнакомцы" for asked in client.asked for word in asked.split()), (
        "к индексерам уходят только слова, названные самим человеком"
    )
    assert "справка нашла лишь похожее имя «Все мы убийцы»" in said


def test_a_guessed_name_with_a_living_lead_does_not_bring_a_stranger() -> None:
    """🔴 TC-359. Догадка справки прикрыта гейтом одинаково, есть вожак или нет.

    Тот же живой случай, что в TC-253, но пул не пуст, а негоден: «Все мы незнакомцы»
    нашлись русскими DVDRip'ами без единого HD, и вожак есть. Гейт подмены
    (:func:`~torrcast.usecases.reinforce.same_picture.same_picture`) от этого не сильнее: он сверяет
    добор со справкой, а оба они тут про одну и ту же чужую картину - и живые раздачи «Все мы
    убийцы» 1952 года вставали в меню рядом со спрошенной картиной. Имя, лишь признанное похожим, в
    индексеры не идёт независимо от того, нашлась картина или нет.
    """
    client = FakeProwlarr(
        {
            "все мы незнакомцы": [
                raw(f"Все мы незнакомцы (2023) DVDRip {i}", i) for i in range(THIN_POOL + 5)
            ],
            "nous sommes tous des assassins": [
                raw(f"Nous.sommes.tous.des.assassins.1952.BDRip.1080p.x264-{i}", 100 + i)
                for i in range(20)
            ],
        }
    )
    about = _knows(
        {
            "все мы незнакомцы": Origin(
                title="Nous sommes tous des assassins", name="Все мы убийцы", guessed=True
            )
        },
    )

    plans, said = search_circle(client, "все мы незнакомцы", about)

    assert client.asked == ["все мы незнакомцы"], "за чужой картиной не ходят и с живым вожаком"
    assert "справка нашла лишь похожее имя «Все мы убийцы»" in said
    assert all(plan.picture.year != 1952 for plan in plans), "чужая картина в меню не встаёт"


def test_a_shorter_article_title_brings_the_real_original() -> None:
    """🔴 TC-283. Прокатное имя на два слова длиннее статьи, но это та же картина."""
    client = FakeProwlarr(
        {
            "all of us strangers": [
                raw(f"All.of.Us.Strangers.2023.1080p.WEB-DL.x264-{i}", i) for i in range(20)
            ]
        }
    )
    about = _knows(
        {"все мы незнакомцы": Origin(title="All of Us Strangers", name="Незнакомцы", guessed=True)},
    )

    plans, said = search_circle(client, "все мы незнакомцы", about)

    assert client.asked == ["все мы незнакомцы", "All of Us Strangers"]
    assert len(plans[0].picture.releases) == 20
    assert "оригинал «All of Us Strangers» - по справке; без неё второго запроса не было бы" in said


def test_the_same_name_in_another_spelling_is_still_topped_up() -> None:
    """А описка в одну букву добор не отменяет: «Сальтберн» и «Солтберн» - одно имя.

    Тут справка называет ТУ ЖЕ картину, только другой транскрипцией, и это и есть второй
    признак: сверять было с чем, и сверка сошлась. Молчим и добираем, как добирали.
    """
    client = FakeProwlarr(
        {"saltburn": [raw(f"Saltburn.2023.1080p.WEB-DL.x264-{i}", i) for i in range(20)]}
    )
    about = _knows({"сальтберн": Origin(title="Saltburn", name="Солтберн", guessed=True)})

    plans, said = search_circle(client, "сальтберн", about)

    assert client.asked == ["сальтберн", "Saltburn"]
    assert len(plans[0].picture.releases) == 20
    assert "сверить было не с чем" not in said


def test_the_same_confirmed_guess_is_topped_up_with_a_living_lead() -> None:
    """Живой вожак гейту не помеха и не послабление: подтверждённая догадка добирает.

    Пара к TC-359: пул негодный (русские DVDRip'ы без HD), справка признала имя лишь
    похожим, но называет ТУ ЖЕ картину другой транскрипцией - второй признак есть, и
    добор работает ровно так, как на пустой выдаче.
    """
    client = FakeProwlarr(
        {
            "сальтберн": [
                raw(f"Сальтберн / Saltburn (2023) DVDRip {i}", i) for i in range(THIN_POOL + 5)
            ],
            "saltburn": [raw(f"Saltburn.2023.1080p.WEB-DL.x264-{i}", 100 + i) for i in range(20)],
        }
    )
    about = _knows({"сальтберн": Origin(title="Saltburn", name="Солтберн", guessed=True)})

    plans, said = search_circle(client, "сальтберн", about)

    assert client.asked == ["сальтберн", "Saltburn"]
    assert len(plans[0].picture.releases) == THIN_POOL + 25
    assert "добрал по «Saltburn»" in said


def test_a_guessed_name_with_nothing_to_check_it_against_is_taken_out_loud() -> None:
    """Сверить догадку нечем - берём, но говорим об этом: за проверенное не выдаём.

    Русская Википедия подписывает аниме латиницей, и своего русского имени у статьи нет
    вовсе. Отказывать тут не за что - имя ничему не противоречит, - но и молчать нельзя:
    человек вправе знать, что картину под его именем выбрала справка, а не выдача.
    """
    client = FakeProwlarr(
        {"re:zero": [raw(f"Re.Zero.S01E{i:02d}.1080p.WEB-DL", i) for i in range(1, 9)]}
    )
    about = _knows({"ре зеро": Origin(title="Re:Zero", guessed=True)})

    plans, said = search_circle(client, "ре зеро", about)

    assert client.asked == ["ре зеро", "Re:Zero"]
    assert len(plans[0].picture.releases) == 8
    assert "имя «Re:Zero» взято со справки, сверить было не с чем" in said


def test_a_name_wikipedia_itself_redirects_to_is_not_a_guess() -> None:
    """Другое русское имя от САМОЙ Википедии - не догадка, и добор ею не отменяется.

    «Мальчик и цапля» - живое перенаправление на статью «Мальчик и птица»: это утверждение
    самой Википедии о том, что картина одна. Сверка имён тут ни при чём, отметки
    ``guessed`` у такого паспорта нет, и всё работает ровно так, как работало.
    """
    client = FakeProwlarr(
        {
            "the boy and the heron": [
                raw(f"The.Boy.and.the.Heron.2023.1080p.BluRay-{i}", i) for i in range(20)
            ]
        }
    )
    about = _knows(
        {"мальчик и цапля": Origin(title="The Boy and the Heron", name="Мальчик и птица")},
    )

    plans, said = search_circle(client, "мальчик и цапля", about)

    assert client.asked == ["мальчик и цапля", "The Boy and the Heron"]
    assert len(plans[0].picture.releases) == 20
    assert "похожее имя" not in said and "сверить было не с чем" not in said


def test_the_reference_original_does_not_open_the_gate_to_another_year() -> None:
    """🔴 Оригинал из справки - proven, но год всё равно сверяется.

    Имя пришло от справки, значит оно про ту самую картину; а вот приехать по нему может
    чужое кино того же названия. Год расходится - добора не было, и это честное
    «не нашлось», а не чужой фильм.
    """
    client = FakeProwlarr(
        {"the ascent": [raw(f"The.Climbers.2019.1080p.WEB-DL.x264-{i}", i) for i in range(20)]}
    )
    about = _knows({"восхождение": Origin(title="The Ascent", year=1976)})

    with pytest.raises(NotFoundError):
        search_circle(client, "восхождение", about)

    assert about.asked == ["восхождение"]
    assert client.asked == ["восхождение", "The Ascent"]


def test_the_verdict_of_a_top_up_comes_after_the_line_of_that_very_search() -> None:
    """Сначала строка круга, потом его итог - иначе это читается как противоречие.

    ``note`` печатается сразу, а строка фазы - только когда фазу закрыли, и в прежнем
    порядке «приехала другая картина» выходило ПЕРЕД «поиск «The Climbers»… 102.1 с».
    Человек читал два несвязанных сообщения как отказ, за которым будто бы последовал
    удавшийся второй поиск, из которого и выросло меню.
    """
    client = _namesakes()
    _plans, said = search_circle(client, "восхождение")

    assert "поиск «The Climbers»" in said
    assert said.index("поиск «The Climbers»") < said.index("приехала другая картина")
    # Итог называет, на чём остались: молчаливого «не беру» человеку мало.
    assert "остаюсь на выдаче по «восхождение»" in said


def test_the_same_name_is_not_asked_a_second_time() -> None:
    """Латинский запрос уже латинский: второй круг тем же именем - чистая трата.

    На «cast cars» оригиналом из выдачи оказывается «Cars», то есть сам запрос, и добор
    уходил на полный круг по всем индексерам за той же самой выдачей: на живом стенде это
    стоило 102 секунды до меню.
    """
    client = FakeProwlarr({"cars": [raw(f"Cars (2006) BDRip {i}", i) for i in range(3)]})
    about = _knows({"cars": Origin(title="Cars", year=2006)})

    plans, _said = search_circle(client, "cars", about)

    assert client.asked == ["cars"]
    # Пул тощий - значит добор рассматривался и был отменён именно как бессмысленный.
    assert max(len(p.picture.releases) for p in plans) < THIN_POOL


def test_latin_query_is_topped_up_by_the_russian_title_from_the_reference() -> None:
    """Спросили латиницей, а живут раздачи под русским именем - добор идёт в другую сторону.

    ``cast cars`` на живом каталоге приносил одну мёртвую англоязычную раздачу: «Тачки»
    индексер по слову ``cars`` не отдаёт вовсе. Русское имя картины знает справка - им и
    добираем, ровно как латинским именем добираем русский запрос.
    """
    client = FakeProwlarr(
        {
            "cars": [raw("Cars (2006) 1080p WEB-DL", 1, seeders=3)],
            "тачки": [raw(f"Тачки / Cars (2006) BDRip {i}", 10 + i) for i in range(4)]
            + [raw(f"Тачки 3 / Cars 3 (2017) BDRip {i}", 20 + i) for i in range(14)],
        }
    )
    about = _knows({"cars": Origin(title="Cars", year=2006, name="Тачки")})

    plans, said = search_circle(client, "cars", about)

    assert client.asked == ["cars", "Тачки"]
    # Картина одна на оба имени: русские раздачи в пуле, а не в соседнем пункте меню.
    cars = next(p for p in plans if p.picture.year == 2006)
    assert cars.picture.title == "Тачки"
    assert len(cars.picture.releases) == 5
    assert "добрал по «Тачки»" in said


def test_the_biggest_part_of_a_franchise_is_not_a_swapped_picture() -> None:
    """Добор по имени от справки приносит франшизу целиком, и вожаком в ней становится
    самая раздаваемая часть. Это не подмена: картина нужного года на месте, и гейт её видит.
    """
    client = FakeProwlarr(
        {
            "cars": [raw("Cars (2006) 1080p WEB-DL", 1, seeders=3)],
            "тачки": [raw(f"Тачки 3 / Cars 3 (2017) BDRip {i}", 20 + i) for i in range(14)]
            + [raw(f"Тачки / Cars (2006) BDRip {i}", 10 + i) for i in range(4)],
        }
    )
    about = _knows({"cars": Origin(title="Cars", year=2006, name="Тачки")})

    plans, said = search_circle(client, "cars", about)

    assert [p.picture.year for p in plans] == [2006, 2017]
    assert "приехала другая картина" not in said


def test_a_classic_with_a_known_original_is_asked_by_it_and_not_by_translit() -> None:
    """Неанглийская классика ищется оригиналом; транслит - запасной ход, а не первый.

    Живой замер (TC-138): «Крики и шёпот» уходили в индексер транслитом
    ``kriki i shepot`` и приносили НОЛЬ строк, тогда как под своим оригиналом
    ``Viskningar och rop`` в том же каталоге лежат девять. Транслит тут не выручает - он
    выдумывает имя, которым раздачу не подписывал никто.
    """
    client = FakeProwlarr(
        {
            "крики и шёпот": [raw("Крики и шёпот (1972) DVDRip", 1)],
            "viskningar och rop": [
                raw(f"Viskningar och rop AKA Cries and Whispers 1972 BDRip {i}", 10 + i)
                for i in range(9)
            ],
        }
    )
    about = _knows({"крики и шёпот": Origin(title="Viskningar och rop", name="Шёпоты и крики")})

    _plans, said = search_circle(client, "крики и шёпот", about)

    assert client.asked == ["крики и шёпот", "Viskningar och rop"]
    assert transliterate("крики и шёпот") not in client.asked
    assert "добрал по «Viskningar och rop»: стало 10" in said


def test_the_swap_of_the_query_is_said_out_loud() -> None:
    """Смена запроса - не молчаливое дело: сказано, что имя от справки и чем искали бы без неё."""
    client = FakeProwlarr(
        {
            "крики и шёпот": [raw("Крики и шёпот (1972) DVDRip", 1)],
            "viskningar och rop": [
                raw(f"Viskningar och rop 1972 BDRip {i}", 10 + i) for i in range(9)
            ],
        }
    )
    about = _knows({"крики и шёпот": Origin(title="Viskningar och rop", name="Шёпоты и крики")})

    _plans, said = search_circle(client, "крики и шёпот", about)

    assert "оригинал «Viskningar och rop» - по справке; без неё искал бы «kriki i shepot»" in said


def test_the_reference_that_says_nothing_new_keeps_quiet() -> None:
    """Справка назвала то же имя, что лежало в выдаче, - объявлять нечего, строки нет."""
    client = _catalog(russian=2, latin=40)
    about = _knows({"психо": Origin(title="Psycho", year=1960)})

    _plans, said = search_circle(client, "психо", about)

    assert "по справке" not in said
    assert "добрал по «Psycho»" in said


def test_an_empty_second_language_round_explains_its_result() -> None:
    """Второй круг без новых строк всё равно называет человеку свой итог."""
    client = FakeProwlarr({"психо": [raw("Психо (1960) DVDRip", 1)]})
    about = _knows({"психо": Origin(title="Psycho", year=1960)})

    _plans, said = search_circle(client, "психо", about)

    assert client.asked == ["психо", "Psycho"]
    assert said.count("добор по «Psycho» ничего не дал") == 1


def test_a_latin_named_picture_without_an_article_keeps_its_translit() -> None:
    """Смежный класс: у латинописанного аниме статьи в русской Википедии нет вовсе.

    «Врата Штейна» подписаны латиницей (``Steins;Gate``), русской статьи под этим именем
    нет, и справка молчит по-честному. Транслит для такой картины - единственное, что
    есть, и отнимать его нельзя: на нём и стоит весь добор.
    """
    client = FakeProwlarr(
        {
            "врата штейна": [raw("Врата Штейна (2011) WEB-DL", 1)],
            "vrata shteyna": [
                raw(f"Vrata Shteyna Steins Gate 2011 BDRip {i}", 10 + i) for i in range(6)
            ],
        }
    )
    about = _knows({})  # статьи нет - паспорт пуст

    _plans, said = search_circle(client, "врата штейна", about)

    assert client.asked == ["врата штейна", "vrata shteyna"]
    assert "по справке" not in said
    assert "добрал по «vrata shteyna»: стало 7" in said


def test_a_query_typed_in_the_wrong_layout_reads_as_russian() -> None:
    """🔴 TC-195. `nfxrb` - это «тачки» клавиша в клавишу, а не транслит."""
    assert unswap_layout("nfxrb") == "тачки"
    assert unswap_layout("rjhgjhfwbz vjycnhjd") == "корпорация монстров"
    assert unswap_layout("NFXRB") == "тачки"


def test_the_layout_swap_keeps_digits_and_spacing() -> None:
    """Номер части в новой строке остаётся номером: «nfxrb 2» → «тачки 2»."""
    assert unswap_layout("nfxrb 2") == "тачки 2"


def test_the_wrong_layout_finds_the_picture_instead_of_refusing() -> None:
    """🔴 TC-195. Ровно первая строка вечера владельца: `cast nfxrb` вместо «cast тачки».

    Прежде это был отказ «по запросу «nfxrb» ничего не нашлось» за 1.8 с при живом
    каталоге. Откат правки роняет тест на ``NotFoundError``.
    """
    client = FakeProwlarr(
        {"тачки": [raw(f"Тачки / Cars (2006) BDRip 1080p {i}", i) for i in range(20)]}
    )

    plans, said = search_circle(client, "nfxrb")

    assert client.asked == ["nfxrb", "тачки"]
    assert plans[0].picture.title.casefold().startswith("тачки")
    # Подмена не молчаливая: человек читает, что за него прочитали.
    assert "в русской раскладке" in said


def test_a_latin_query_that_finds_something_is_never_re_read_as_layout() -> None:
    """«cars» находит своё, и второго захода («сфкы») не случается вовсе - ни секунды."""
    client = FakeProwlarr(
        {"cars": [raw(f"Cars.2006.1080p.BluRay.x264-GRP{i}", i) for i in range(20)]}
    )

    _plans, said = search_circle(client, "cars")

    assert client.asked == ["cars"]
    assert "раскладке" not in said


def test_a_picture_dubbed_only_in_unplayable_releases_is_asked_by_original_and_year() -> None:
    """🔴 TC-210. «Тачки»: по-русски одни образы DVD, играбельное - англоязычный рип.

    Живая выдача первой части: все русские раздачи оказались DVD-образами (играть в них
    нечего, и отбор не берёт их по делу), а единственным кандидатом остаётся
    ``Cars 2006 BluRay 1080p`` на 66 сид - без русской дорожки. Добор вторым языком сюда
    уже сходил и принёс ровно его: по слову ``Cars`` индексер отдаёт первую сотню строк,
    и русского ``BDRip 1080p | D`` в ней нет.

    Разводит эту сотню ГОД: точная строка ``Cars 2006`` приносит «Тачки / Cars (2006)
    BDRip 1080p | D» на 61 сид - честный 1080p с дубляжом и вчетверо легче образа диска.
    """
    about = _knows({"тачки": Origin(title="Cars", year=2006, name="Тачки")})
    client = FakeProwlarr(
        {
            "тачки": [
                raw(f"Тачки / Cars [2006, США, мультфильм, DVD9] дубляж {i}", i, seeders=4)
                for i in range(3)
            ],
            "cars": [raw("Cars 2006 BluRay 1080p DDP 5 1 x264-hallowed", 10, seeders=66)],
            "cars 2006": [
                raw("Тачки / Cars (2006) BDRip 1080p | D", 20, seeders=61, size=4.4 * GB)
            ],
        }
    )

    plans, said = search_circle(client, "тачки", about)

    assert client.asked == ["тачки", "Cars", "Cars 2006"]
    line = phrase("reinforce.voice_note", title="Тачки", exact="Cars 2006", now=0)
    line = line.split(": ", 1)[0]
    assert line in said
    top = plans[0].ranked[0]
    assert top.dubbed, "верхом стоит раздача с русской дорожкой, а не англоязычный рип"
    assert "BDRip 1080p | D" in top.raw_name


def test_a_dub_locked_behind_the_bitrate_ceiling_is_asked_by_original_and_year() -> None:
    """🔴 TC-211. «Тачки 2»: дубляж обещан только 4К-ремуксом, который отбор не берёт.

    Кандидатом у второй части стоит ремукс на 27 ГБ, о звуке молчащий, а дубляж назван в
    38-гигабайтном 2160p - и тот не проходит потолок битрейта (:func:`over_ceiling`)
    задолго до всякого ffprobe. Отказывать потолком нельзя (ремукс такого веса и правда
    не сыграть), но и вечера по-русски так не выходит.

    Номер части у добора вторым языком отрезан разбором франшизы, поэтому он уходит
    словом ``Cars`` и не приносит ничего. Точная строка собирается по самой картине -
    ``Cars 2 2011``, - и приносит «Тачки 2 / Cars 2 (2011) BDRip 1080p» на 11 сид: пять
    гигабайт, дубляж, никакого сплошного перекода.
    """
    about = _knows({"тачки": Origin(title="Cars", year=2006, name="Тачки")})
    client = FakeProwlarr(
        {
            "тачки": [
                raw(
                    "Тачки 2 / Cars 2 [2011, США, мультфильм, BDRemux 1080p] "
                    "[Локализованный видеоряд]",
                    1,
                    seeders=71,
                    size=27 * GB,
                ),
                raw(
                    "Тачки 2 / Cars 2 [2011, США, мультфильм, UHD BDRemux 2160p, HDR10] "
                    "Dub + Ukr + Original (Eng)",
                    2,
                    seeders=126,
                    size=38 * GB,
                ),
            ],
            "cars 2 2011": [
                raw(
                    "Тачки 2 / Cars 2 (2011) BDRip 1080p от Leonardo and Scarabey-Лицензия",
                    3,
                    seeders=11,
                    size=5.3 * GB,
                )
            ],
        }
    )

    plans, said = search_circle(client, "тачки 2", about)

    assert client.asked == ["тачки", "Cars", "Cars 2 2011"]
    prefix = phrase(
        "reinforce.voice_note", title="Тачки 2", exact="EXACT-MARK", now="NOW-MARK"
    ).split(" - ")[0]
    assert prefix in said
    top = plans[0].ranked[0]
    assert top.dubbed and top.height == 1080, "верх - честный 1080p с дубляжом"
    assert "Leonardo" in top.raw_name
