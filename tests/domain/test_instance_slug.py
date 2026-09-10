"""Зеркало :mod:`torrcast.domain.instance`: метка экземпляра по пути его состояния."""

from __future__ import annotations

import pytest

from torrcast.domain.instance_slug import DEFAULT_STATE, STATE_ENV, instance_slug


def test_the_default_state_path_means_the_plain_host_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Боевой экземпляр на узле один - его имена и места остаются без суффикса."""
    monkeypatch.delenv(STATE_ENV, raising=False)
    assert instance_slug() == ""
    monkeypatch.setenv(STATE_ENV, DEFAULT_STATE)
    assert instance_slug() == ""


def test_each_lane_state_path_gets_its_own_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """Две полосы стенда на одном узле обязаны различаться меткой (TC-1137).

    Без неё обе делили юнит ``torrcast-play`` и каталог ``/dev/shm/torrcast``, и показ
    одной гасил показ другой.
    """
    monkeypatch.setenv(STATE_ENV, "/root/полоса-а-state.json")
    first = instance_slug()
    monkeypatch.setenv(STATE_ENV, "/root/полоса-б-state.json")
    second = instance_slug()

    assert first and second
    assert first != second
    assert not set(first) & set(" /.@\t"), "метка уезжает в имя юнита как есть"


def test_the_mark_is_stable_for_the_same_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Запускающий и юнит считают метку по одной строке и обязаны сойтись на ней."""
    monkeypatch.setenv(STATE_ENV, "/root/полоса-а-state.json")

    assert instance_slug() == instance_slug()
