"""Зеркало :mod:`torrcast.domain.indexer_health`."""

import pytest

from torrcast.domain.indexer_health import CORE_INDEXERS, IPV4_ONLY, IndexerHealth


@pytest.fixture(autouse=True)
def _russian_lines(_russian_product: None) -> None:
    """Предмет модуля - русское словоблюдие самопроверки, поэтому язык назван вслух.

    Умолчание продукта английское (:mod:`torrcast.domain.catalogs.tongue`), и без этой
    строки набор мерил бы английские надписи, а рассказывал бы про русские.
    """


def test_the_road_to_trackers_is_named_and_treated() -> None:
    """🔴 TC-311: по IPv6 ответ трекера обрывается раньше, чем по IPv4."""
    sick, ok = IndexerHealth.route("Environment=LANG=ru_RU.UTF-8")
    assert ok and sick.startswith("внимание"), sick
    assert IPV4_ONLY in sick, "у строки должно быть лечение, а не только диагноз"
    assert IndexerHealth.route(f"Environment={IPV4_ONLY}")[0].startswith("ок")


def test_an_unmanaged_service_is_a_warning() -> None:
    """Службы у нас нет - дорогу не видно, но и утверждать про неё нечего."""
    line, ok = IndexerHealth.route(None)
    assert ok and "не управляем" in line, line


def test_an_empty_apikey_is_a_failure_before_any_network() -> None:
    """Пустой ключ - искать нечем; строка сразу говорит, чем это лечится."""
    line, ok = IndexerHealth.no_apikey()
    assert not ok and "install.sh" in line, line


def test_zero_indexers_is_a_failure_and_a_count_is_not() -> None:
    """Отвечающий Prowlarr без индексеров ищет ровно ничего."""
    assert IndexerHealth.count("http://x", 0)[1] is False
    line, ok = IndexerHealth.count("http://x", 4)
    assert ok and "индексеров 4" in line


def test_a_silent_prowlarr_is_a_failure() -> None:
    line, ok = IndexerHealth.silent("http://x")
    assert not ok and "не отвечает" in line, line


def test_a_pause_is_reported_by_name_and_not_by_number() -> None:
    """Голый номер индексера человеку ничего не говорит, имя - говорит."""
    lines = list(
        IndexerHealth.paused(
            [{"id": 7, "name": "RuTor"}],
            [{"indexerId": 7, "disabledTill": "2026-08-09T12:30:00Z"}],
        )
    )
    assert lines == [("плохо   индексер RuTor отключён Prowlarr до 2026-08-09 12:30:00", False)]


def test_a_pause_of_an_unknown_indexer_still_leaves_a_line() -> None:
    """Имени нет - показываем номер: молчать о паузе нельзя в любом случае."""
    lines = list(IndexerHealth.paused([], [{"indexerId": 9, "disabledTill": "завтра"}]))
    assert lines and "индексер 9" in lines[0][0]


def test_junk_instead_of_lists_produces_no_pauses() -> None:
    assert list(IndexerHealth.paused("мусор", [])) == []
    assert list(IndexerHealth.paused([], "мусор")) == []


def test_only_enabled_indexers_with_a_number_are_probed() -> None:
    """Живой поиск идёт по тем, кто вообще ищет и кого можно назвать номером."""
    payload = [
        {"id": 1, "name": "RuTor", "enable": True},
        {"id": 2, "name": "Nyaa", "enable": False},
        {"id": "нет", "name": "Kinozal"},
        {"id": 4},
        "мусор",
    ]
    assert IndexerHealth.probed(payload) == [(1, "RuTor")]
    assert IndexerHealth.probed("не список") == []


def test_every_answer_of_a_live_probe_has_its_own_line() -> None:
    """Молчание и ответ мимо - разные диагнозы, и обе строки красные."""
    assert IndexerHealth.answered("RuTor", "answered")[1] is True
    mimo, ok = IndexerHealth.answered("AniLibria", "irrelevant")
    assert not ok and "мимо контрольного запроса" in mimo
    silent, ok = IndexerHealth.answered("RuTor", "silent")
    assert not ok and "не ответил на живой поиск" in silent


def test_an_anime_indexer_is_asked_about_anime() -> None:
    """Общий контрольный запрос аниме-индексер не знает - он и промолчал бы."""
    assert IndexerHealth.query("AniLibria") == "Kaiba"
    assert IndexerHealth.query("RuTor") == "matrix"


def test_a_fuzzy_answer_past_the_query_is_not_an_answer() -> None:
    """Нечёткое совпадение мимо запроса - это ненадёжная выдача, а не здоровье."""
    assert IndexerHealth.answer("Kaiba", ["Наруто"]) == "irrelevant"
    assert IndexerHealth.answer("Kaiba", ["kaiba 01"]) == "answered"
    assert IndexerHealth.answer("matrix", [""]) == "answered"
    assert IndexerHealth.answer("matrix", []) == "silent"
    assert IndexerHealth.answer("matrix", None) == "silent"


def test_names_survive_junk_rows() -> None:
    """Мусор в ответе не роняет разбор: берём только строковые имена включённых."""
    payload = [{"name": "RuTor"}, "мусор", {"enable": True}, {"name": 7}, None]
    assert IndexerHealth.enabled_names(payload) == ["RuTor"]
    assert IndexerHealth.enabled_names("не список") == []


def test_every_core_source_gets_its_own_line() -> None:
    """🔴 TC-697. Опорных ДВА, и доктор обязан назвать каждого своей строкой.

    Установка при непроходе опорного отправляет человека смотреть именно в `cast doctor`;
    строка только про метапоиск оставляла второй опорный без ответа ровно там, куда за
    ответом послали. Вердикт при этом не валится: без опорного искать всё ещё можно.
    """
    lines = list(IndexerHealth.core([{"name": "RuTor"}]))

    assert len(lines) == len(CORE_INDEXERS) == 2
    missing, present = lines
    assert missing[1] and missing[0].startswith("внимание") and "Knaben" in missing[0]
    assert "аниме" in missing[0] and "./install.sh" in missing[0]
    assert present[1] and present[0].startswith("ок") and "RuTor" in present[0]


def test_a_disabled_core_source_counts_as_missing() -> None:
    """Заведён, но выключен - искать он не будет, значит для вердикта его нет."""
    disabled = [{"name": name, "enable": False} for name in CORE_INDEXERS]
    assert all(line.startswith("внимание") for line, _ in IndexerHealth.core(disabled))
    assert all(
        line.startswith("ок")
        for line, _ in IndexerHealth.core([{"name": n} for n in CORE_INDEXERS])
    )
