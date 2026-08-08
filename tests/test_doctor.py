"""``cast doctor``: вес метапоиска в вердикте.

Каталог держится на одном метапоисковом индексере: прямые трекеры его не перекрывают.
Поиск без него работает, поэтому вердикт остаётся проходным - но строка про неполную
выдачу обязана быть, иначе урезанный каталог выглядит как поиск без причины.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from torrcast import doctor
from torrcast.doctor import KEY_INDEXER
from torrcast.state import Config

if TYPE_CHECKING:
    import pytest


def _config() -> Config:
    return Config(prowlarr_url="http://127.0.0.1:9696", prowlarr_apikey="x" * 32)


def _answers(monkeypatch: pytest.MonkeyPatch, indexers: object) -> None:
    """Ответы Prowlarr без сети: здоровье пустое, список индексеров - из теста."""

    def fake(url: str, headers: dict[str, str]) -> object | None:
        return indexers if url.endswith("/api/v1/indexer") else []

    monkeypatch.setattr(doctor, "_json", fake)


def _lines(monkeypatch: pytest.MonkeyPatch, indexers: object) -> list[tuple[str, bool]]:
    _answers(monkeypatch, indexers)
    return list(doctor._prowlarr(_config()))


def _entry(name: str, enable: bool = True) -> dict[str, Any]:
    return {"name": name, "enable": enable}


def test_key_indexer_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Метапоиск на месте: строка про него зелёная, вердикт проходной."""
    lines = _lines(monkeypatch, [_entry(KEY_INDEXER), _entry("RuTor")])
    assert [ok for _, ok in lines] == [True, True]
    assert "индексеров 2" in lines[0][0]
    assert KEY_INDEXER in lines[1][0]
    assert lines[1][0].startswith("ок")


def test_key_indexer_missing_is_loud_but_passing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Метапоиска нет: вердикт не валится, но про неполную выдачу сказано словами."""
    lines = _lines(monkeypatch, [_entry("RuTor"), _entry("Nyaa.si")])
    text = lines[1][0]
    assert lines[1][1] is True
    assert text.startswith("внимание")
    assert KEY_INDEXER in text
    assert "аниме" in text


def test_key_indexer_disabled_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Заведён, но выключен - искать он не будет, значит для вердикта его нет."""
    lines = _lines(monkeypatch, [_entry(KEY_INDEXER, enable=False), _entry("RuTor")])
    assert lines[1][0].startswith("внимание")


def test_no_indexers_at_all_is_bad(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустой список - это по-прежнему «плохо», и строки про метапоиск уже нет."""
    lines = _lines(monkeypatch, [])
    assert len(lines) == 1
    assert lines[0][1] is False


def test_names_survive_junk_rows() -> None:
    """Мусор в ответе не роняет разбор: берём только строковые имена включённых."""
    payload = [_entry("RuTor"), "мусор", {"enable": True}, {"name": 7}, None]
    assert doctor._enabled_names(payload) == ["RuTor"]
    assert doctor._enabled_names("не список") == []
