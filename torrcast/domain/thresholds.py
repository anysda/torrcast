"""Собирает действующие пороги телевизора и источник каждого значения."""

from typing import Final, Protocol

from torrcast.domain.profile import CAUTIOUS, Profile

__all__ = ["thresholds"]

_TUNED: Final = {
    "hls_segment": "segment_seconds",
    "hls_burst": "burst",
    "bitrate_warn_mbit": "warn_mbit",
    "recode_at_mbit": "recode_at_mbit",
    "recode_mbit": "recode_mbit",
}
_CONFIG_THRESHOLDS: Final = (
    "hls_segment",
    "hls_keyframes",
    "hls_burst",
    "bitrate_warn_mbit",
    "bitrate_hard_mbit",
    "bitrate_recode_mbit",
    "recode",
    "recode_at_mbit",
    "recode_mbit",
    "recode_head_wait",
    "recode_tonemap",
)
_PROFILE_THRESHOLDS: Final = (
    "recode_codecs",
    "copy_depth",
    "copy_codecs",
    "recode_frame",
    "max_segment_bytes",
    "start_buffer",
    "hold_seconds",
    "patience",
    "app_patience",
    "dead_url_seconds",
    "load_retries",
    "segment_retries",
    "sulk",
    "revive_timeout",
    "revive_pause",
    "revive_drop",
    "stall_seconds",
    "ready_ahead",
    "stall_skip",
    "blind_nudges",
)


class _Config(Protocol):
    def __getattribute__(self, name: str) -> object: ...


def thresholds(
    raw: _Config, tuned: _Config, profile: Profile, configured: frozenset[str]
) -> tuple[dict[str, object], dict[str, str]]:
    """Вернуть значения действующих порогов и безопасные подписи источников."""
    values: dict[str, object] = {}
    sources: dict[str, str] = {}
    for key in _CONFIG_THRESHOLDS:
        values[key] = getattr(tuned, key)
        if key in _TUNED:
            stock = getattr(CAUTIOUS, _TUNED[key])
            if getattr(raw, key) != stock:
                sources[key] = "написан в конфиге"
            elif key in configured:
                # Ключ в файле ЕСТЬ, но равен осторожному умолчанию, а tune() такой
                # считает несказанным: играет профиль, и молчать об этом - значит
                # показать согласие там, где настройку проигнорировали.
                sources[key] = f"написан в конфиге, но равен осторожному - профиль {profile.key}"
            else:
                sources[key] = f"профиль {profile.key}"
        else:
            sources[key] = "написан в конфиге" if key in configured else "умолчание конфига"
    for key in _PROFILE_THRESHOLDS:
        value = getattr(profile, key)
        values[key] = sorted(value) if isinstance(value, frozenset) else value
        sources[key] = f"профиль {profile.key}"
    return values, sources
