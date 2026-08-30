"""Tests for the effective receiver-threshold snapshot."""

from torrcast.domain.config import Config
from torrcast.domain.profile import ANDROID_TV
from torrcast.domain.thresholds import thresholds
from torrcast.domain.tune import tune


def test_snapshot_names_profile_and_explicit_configuration() -> None:
    raw = Config(hls_segment=8.0)
    values, sources = thresholds(raw, raw, ANDROID_TV, frozenset({"hls_segment"}))
    assert values["patience"] == 577.0
    assert sources["patience"] == "profile androidtv"
    assert sources["hls_segment"] == "written in the config"


def test_a_handwritten_key_equal_to_the_cautious_default_is_not_silent() -> None:
    """Ключ в файле ЕСТЬ, но равен осторожному умолчанию: играет профиль, и лента
    обязана это сказать - иначе человек читает согласие там, где его настройку
    молча проигнорировали."""
    raw = Config(recode_at_mbit=10.0)  # 10.0 - осторожное умолчание, написанное руками
    tuned = tune(raw, ANDROID_TV)
    values, sources = thresholds(raw, tuned, ANDROID_TV, frozenset({"recode_at_mbit"}))

    assert values["recode_at_mbit"] == 28.0, "играет профиль, а не написанное"
    assert sources["recode_at_mbit"] == (
        "written in the config, but equal to the cautious one - profile androidtv"
    )


def test_an_unwritten_key_still_names_the_profile_plainly() -> None:
    """Ключа в файле нет - источник просто «профиль», без «написан в конфиге»."""
    raw = Config()
    _values, sources = thresholds(raw, raw, ANDROID_TV, frozenset())

    assert sources["recode_at_mbit"] == "profile androidtv"
