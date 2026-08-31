"""Проверки слоя строк Telegram: язык спрашивается у единого держателя продукта."""

from pathlib import Path

from pytest import MonkeyPatch

from tgbot.catalogs.en import en as english
from tgbot.catalogs.ru import ru as russian
from tgbot.i18n import _failure_detail, i18n
from torrcast.domain.invalid_config_object_error import InvalidConfigObjectError


def test_the_layer_speaks_the_language_of_the_one_holder(_russian_product: None) -> None:
    """Язык не приходит параметром-снимком: один и тот же ключ следует за держателем."""
    assert i18n("invalid_choice") == russian()["invalid_choice"]


def test_english_is_default_and_russian_is_explicit(_english: None) -> None:
    assert i18n("invalid_choice") == english()["invalid_choice"]


def test_the_environment_cannot_choose_the_default(
    monkeypatch: MonkeyPatch, _english: None
) -> None:
    """``TORRCAST_LANGUAGE`` - договор установщика; на живой ответ среда не влияет."""
    monkeypatch.setenv("TORRCAST_LANGUAGE", "ru")

    assert i18n("invalid_choice") == english()["invalid_choice"]


def test_a_structured_refusal_is_translated_past_the_frame(_russian_product: None) -> None:
    """Слово беды переводится вслед за рамкой ответа, а не остаётся английским внутри."""
    detail = _failure_detail(InvalidConfigObjectError(Path("conf.json"), "broken"))

    assert detail == russian()["invalid_config_object"].format(path=Path("conf.json"))
