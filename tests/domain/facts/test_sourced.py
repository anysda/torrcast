"""Проверяет подпись ответа справки его источником."""

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_MAP, SOURCE_WIKI
from torrcast.domain.facts.sourced import sourced


def test_an_answer_is_signed_by_the_one_who_knows_its_source() -> None:
    """🔴 TC-450. Сам по себе паспорт рассказать этого не может - подписывает место вызова."""
    assert sourced(Origin(title="Cars"), SOURCE_WIKI).source == SOURCE_WIKI


def test_an_already_signed_answer_is_never_signed_again() -> None:
    """Иначе ответ карты, пришедший последним шагом, выдал бы себя за Википедию."""
    map_answer = Origin(title="Cars", source=SOURCE_MAP)
    assert sourced(map_answer, SOURCE_WIKI).source == SOURCE_MAP


def test_silence_is_not_signed_at_all() -> None:
    """Пустой паспорт источника не имеет: приписывать некому и нечего."""
    assert sourced(Origin(), SOURCE_WIKI) == Origin()
