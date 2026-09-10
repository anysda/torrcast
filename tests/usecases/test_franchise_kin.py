"""Проверяет полку родни картины: паспорт даёт Q-идентификатор, кэш стоит перед сетью."""

from dataclasses import dataclass, field

from tests.fakes.kin_source import FakeKinSource
from tests.fakes.kin_store import FakeKinStore
from tests.fakes.passport import FakePassport
from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.franchise_kin import FranchiseKin


@dataclass
class TypedPassport:
    """Паспорт, различающий род: у фильма и сериала статьи разные, и ответы тоже.

    Общий :class:`tests.fakes.passport.FakePassport` знает только имя, а весь предмет
    здесь - именно род: ``series=None`` это режим «оба типа», которым продукт спрашивает,
    когда подсказанный род не дал статьи.
    """

    known: dict[bool | None, Origin] = field(default_factory=dict)
    asked: list[bool | None] = field(default_factory=list)

    def __call__(self, title: str, series: bool | None = False, budget: float = 0.0) -> Origin:
        self.asked.append(series)
        return self.known.get(series, Origin())


def test_the_entity_from_the_passport_is_what_wikidata_gets_asked_about() -> None:
    """Полка спрашивает Wikidata по Q-идентификатору картины, а не по её имени."""
    passport = FakePassport({"Крепкий орешек": Origin(title="Die Hard", entity="Q105598")})
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    kin = FakeKinSource(lambda entity, timeout: found if entity == "Q105598" else [])

    shelf = FranchiseKin(passport, kin, FakeKinStore(), FakePassport())
    got = shelf.of("Крепкий орешек", False, 1.0)

    assert got == found
    assert kin.asked == ["Q105598"]


def test_a_picture_without_an_entity_never_reaches_wikidata() -> None:
    """Без Q-идентификатора спрашивать Wikidata не о чем - полка пуста без похода."""
    passport = FakePassport({"Неизвестное кино": Origin(title="Unknown", source="wiki")})
    kin = FakeKinSource()

    shelf = FranchiseKin(passport, kin, FakeKinStore(), FakePassport())
    assert shelf.of("Неизвестное кино", False, 1.0) == []
    assert kin.asked == []


def test_a_silent_passport_is_not_an_empty_franchise() -> None:
    """Офлайн-паспорт без QID не доказывает, что Wikidata ответила пустым списком."""
    passport = FakePassport({"Форсаж": Origin(title="The Fast and the Furious", source="map")})
    shelf = FranchiseKin(passport, FakeKinSource(), FakeKinStore(), passport)

    assert shelf.of("Форсаж", False, 1.0) is None


def test_a_second_ask_for_the_same_picture_never_touches_the_network() -> None:
    """🔴 Второй заход за той же картиной не ходит в сеть - отвечает кэш на диске."""
    passport = FakePassport({"Крепкий орешек": Origin(title="Die Hard", entity="Q105598")})
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    kin = FakeKinSource(lambda entity, timeout: found)
    store = FakeKinStore()
    shelf = FranchiseKin(passport, kin, store, FakePassport())

    assert shelf.of("Крепкий орешек", False, 1.0) == found
    assert shelf.of("Крепкий орешек", False, 1.0) == found

    assert kin.asked == ["Q105598"], "второй заход обязан отвечать кэшем, а не сетью"


def test_a_franchise_without_kin_is_remembered_as_an_empty_shelf() -> None:
    """Пустой ответ тоже кэшируется - без этого каждый показ бил бы по сети заново."""
    passport = FakePassport({"Одинокое кино": Origin(title="Lonely", entity="Q1")})
    kin = FakeKinSource(lambda entity, timeout: [])
    store = FakeKinStore()
    shelf = FranchiseKin(passport, kin, store, FakePassport())

    assert shelf.of("Одинокое кино", False, 1.0) == []
    assert shelf.of("Одинокое кино", False, 1.0) == []
    assert kin.asked == ["Q1"]


def test_a_silent_network_leaves_no_row_in_the_cache() -> None:
    """🔴 Молчание сети не кладётся в кэш: ряд на диске переживёт и показ, и обновление.

    Разница с пустым ответом - вся суть: «родни нет» продукт узнал и отвечает списком,
    а «сеть молчит» не узнал ничего и отвечает ``None`` - незаконченным, чтобы следующий
    заход спросил заново. Замер 07-09-2026 на стенде `.104`: «Форсаж» лёг пустым рядом
    от одной оборванной связи и отвечал пусто за 0,0 с, пока живой запрос давал десять
    картин.
    """
    passport = FakePassport({"Форсаж": Origin(title="The Fast and the Furious", entity="Q1")})
    calls: list[str] = []

    def silence(entity: str, timeout: float) -> list[Kin]:
        calls.append(entity)
        raise OSError("HTTP 429")

    store = FakeKinStore()
    shelf = FranchiseKin(passport, FakeKinSource(silence), store, FakePassport())

    assert shelf.of("Форсаж", False, 1.0) is None
    assert store.written == [], "молчание сети записано в кэш пустой полкой"
    assert shelf.of("Форсаж", False, 1.0) is None
    assert calls == ["Q1", "Q1"], "второй заход обязан спросить сеть заново"


def test_a_degraded_passport_is_asked_again_live() -> None:
    """🔴 TC-1114. Паспорт офлайн-карты без Q-идентификатора переспрашивается живьём.

    Такой ряд ложится в кэш бессрочно в минуту молчания Википедии, и без переспроса
    полка глохла навсегда ещё до похода в Wikidata: замер 10-09-2026 на стенде `.104` -
    «Крепкий орешек» и «Форсаж» лежали в `facts.json` с пустым ``entity`` при живых
    сериях по четыре и десять картин.
    """
    cached = FakePassport({"Крепкий орешек": Origin(title="Die Hard", year=1988, source="map")})
    fresh = FakePassport(
        {"Крепкий орешек": Origin(title="Die Hard", year=1988, entity="Q105598", source="wiki")}
    )
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    kin = FakeKinSource(lambda entity, timeout: found)

    got = FranchiseKin(cached, kin, FakeKinStore(), fresh).of("Крепкий орешек", False, 1.0)

    assert got == found
    assert fresh.asked == ["Крепкий орешек"]
    assert kin.asked == ["Q105598"]


def test_a_kind_named_by_the_releases_does_not_get_to_silence_the_whole_shelf() -> None:
    """🔴 Род пришёл из разбора раздач, и статьи под ним нет - спрашиваем «оба типа».

    Замер 10-09-2026 на стенде `.104`: лучшим совпадением на «Чужой» продукт называет
    `tv:чужой:2021`, статьи о сериале с таким именем нет вовсе, и полка стояла пустой
    при шести частях франшизы у фильма 1979 года.
    """
    passport = TypedPassport({None: Origin(title="Alien", entity="Q103569", source="wiki")})
    found = [Kin("Q104814", "Чужие", 1986)]
    kin = FakeKinSource(lambda entity, timeout: found if entity == "Q103569" else [])

    shelf = FranchiseKin(passport, kin, FakeKinStore(), FakePassport())
    got = shelf.of("Чужой", True, 1.0)

    assert got == found
    assert passport.asked == [True, None], "режим «оба типа» обязан идти ПОСЛЕ подсказанного"
    assert kin.asked == ["Q103569"]


def test_a_show_that_really_has_no_franchise_keeps_its_empty_shelf() -> None:
    """Молчат оба типа - полка честно пуста, и Wikidata об этом не спрашивают вовсе.

    Отрицательный полюс соседней проверки: переспрос «обоими типами» не выдумывает родню
    там, где её нет, - :class:`~torrcast.usecases.passport_either.PassportEither` молчит,
    когда фильм и сериал одного имени расходятся или молчат оба.
    """
    passport = TypedPassport({True: Origin(source="wiki"), None: Origin(source="wiki")})
    kin = FakeKinSource()

    shelf = FranchiseKin(passport, kin, FakeKinStore(), FakePassport())

    assert shelf.of("Сериал без франшизы", True, 1.0) == []
    assert passport.asked == [True, None]
    assert kin.asked == []


def test_a_named_kind_that_answers_is_never_second_guessed() -> None:
    """Подсказанный род дал Q-идентификатор - «оба типа» не спрашиваются: тип известен."""
    passport = TypedPassport({True: Origin(title="Fargo", entity="Q1", source="wiki")})
    found = [Kin("Q2", "Фарго, сезон 2", 2015)]
    kin = FakeKinSource(lambda entity, timeout: found)

    shelf = FranchiseKin(passport, kin, FakeKinStore(), FakePassport())

    assert shelf.of("Фарго", True, 1.0) == found
    assert passport.asked == [True], "тип назван и подтверждён статьёй - переспрашивать нечего"


def test_a_wiki_passport_without_an_entity_is_not_reasked() -> None:
    """Статья прочитана, а Q-идентификатора у неё нет - переспрос того же ответа пуст."""
    passport = FakePassport({"Короткометражка": Origin(title="Short", source="wiki")})
    fresh = FakePassport()
    kin = FakeKinSource()

    got = FranchiseKin(passport, kin, FakeKinStore(), fresh).of("Короткометражка", False, 1.0)

    assert got == []
    assert fresh.asked == []
    assert kin.asked == []
