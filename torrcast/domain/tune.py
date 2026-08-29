"""Накладывает пороги профиля телевизора на не переопределённые настройки."""

from dataclasses import replace
from typing import Protocol, TypeVar

from torrcast.domain.profile import CAUTIOUS, Profile

__all__ = ["tune"]


class _Config(Protocol):
    @property
    def hls_segment(self) -> float: ...

    @property
    def hls_burst(self) -> float: ...

    @property
    def bitrate_warn_mbit(self) -> float: ...

    @property
    def recode_at_mbit(self) -> float: ...

    @property
    def recode_mbit(self) -> float: ...

    @property
    def hls_jump(self) -> float: ...

    @property
    def hls_seam_lead(self) -> float: ...


_C = TypeVar("_C", bound=_Config)


def tune(config: _C, profile: Profile) -> _C:
    """Заменить только значения, равные осторожным умолчаниям."""
    return replace(  # type: ignore[type-var]
        config,
        hls_segment=_said(config.hls_segment, CAUTIOUS.segment_seconds, profile.segment_seconds),
        hls_burst=_said(config.hls_burst, CAUTIOUS.burst, profile.burst),
        bitrate_warn_mbit=_said(config.bitrate_warn_mbit, CAUTIOUS.warn_mbit, profile.warn_mbit),
        recode_at_mbit=_said(
            config.recode_at_mbit, CAUTIOUS.recode_at_mbit, profile.recode_at_mbit
        ),
        recode_mbit=_said(config.recode_mbit, CAUTIOUS.recode_mbit, profile.recode_mbit),
        hls_jump=_said(config.hls_jump, CAUTIOUS.jump, profile.jump),
        hls_seam_lead=_said(config.hls_seam_lead, CAUTIOUS.seam_lead, profile.seam_lead),
    )


def _said(mine: float, stock: float, wanted: float) -> float:
    return mine if mine != stock else wanted
