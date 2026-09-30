"""Снимок порогов начала серии: чем играем и откуда взято каждое число."""

from __future__ import annotations

from torrcast.adapters.filesystem.state.config_keys import config_keys
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.profile import Profile
from torrcast.domain.thresholds import thresholds
from torrcast.domain.torrcast_error import TorrcastError


def trace_thresholds(config: Config, profile: Profile, how: str) -> dict[str, object]:
    """Прочитать сохранённые настройки и собрать снимок порогов начала серии.

    ``how`` - источник того выбора, которым играет показ (с поправкой вкладки,
    :func:`torrcast.domain.for_tab.for_tab`). Второй раз приёмник здесь не спрашивается:
    детектор без ключа вкладки назвал бы в ленте «осторожный» рядом с ``profile: browser``.

    Снимок берётся на каждой серии, поэтому непрочитанный конфиг - это строка в ленте,
    а не конец показа.
    """
    try:
        raw = load_config()
    except TorrcastError:
        return {"profile_source": phrase("runtime.config_unread")}
    values, sources = thresholds(raw, config, profile, config_keys())
    return {
        "profile_source": (
            phrase("runtime.receiver_passport")
            if how.startswith(phrase("profile_detector.by_passport_prefix"))
            else how
        ),
        "thresholds": values,
        "threshold_sources": sources,
    }
