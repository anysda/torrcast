"""Проверяет пороги и сроки справки: их читают правила и адаптеры."""

from torrcast.domain.facts import settings


def test_the_menu_budget_is_larger_than_one_request_and_smaller_than_the_topup() -> None:
    """Запросов два, и второй зависит от первого; кэш дописывается уже после меню."""
    assert settings.HTTP_TIMEOUT < settings.FACTS_BUDGET < settings.TOPUP_LIMIT


def test_an_empty_answer_is_remembered_for_a_finite_week() -> None:
    """Срок конечный - статью могли и написать."""
    assert settings.EMPTY_TTL == 7 * 24 * 3600


def test_the_rules_number_is_a_positive_integer_counting_from_one() -> None:
    """Номер правил целый и начинается с единицы: ряд без номера старше любой метки."""
    assert isinstance(settings.FACTS_RULES, int) and settings.FACTS_RULES >= 1


def test_the_dumps_live_beside_the_state_of_the_service() -> None:
    """Оба файла кладёт `install.sh`; нет их - справка молчит, и это не сбой."""
    assert settings.RATINGS_PATH.name == "imdb-ratings.tsv"
    assert settings.RU_NAMES_PATH.name == "imdb-ru-names.tsv"


def test_the_source_marks_are_short_words_joined_by_a_plus() -> None:
    """🔴 TC-450. «wiki+map» читается глазом и считается grep'ом по сохранённому прогону."""
    assert settings.SOURCE_JOIN.join([settings.SOURCE_WIKI, settings.SOURCE_MAP]) == "wiki+map"
    assert settings.SOURCE_WIKIDATA == "wikidata"


def test_the_batch_of_names_is_the_api_limit_taken_three_times() -> None:
    """В один запрос влезает двадцать имён, а у меню их под сотню."""
    assert settings._EXLIMIT == 20
    assert settings._EXBATCHES == 3
