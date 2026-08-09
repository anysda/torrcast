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


def _sets(monkeypatch: pytest.MonkeyPatch, size: int, disk: bool = False) -> None:
    monkeypatch.setattr(doctor, "_settings", lambda url: {"CacheSize": size, "UseDisk": disk})


def test_cache_fits_the_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кэш, который вместе со своим перерасходом влезает в память, - строка «ок» с цифрой."""
    _sets(monkeypatch, 3 * 1024**3)
    monkeypatch.setattr(doctor, "machine_memory", lambda: 8 * 1024**3)
    line, good = doctor._cache(_config())
    assert good, "3 ГиБ кэша на 8 ГиБ машины - это норма, а не поломка"
    assert "3.0 ГиБ" in line and "8.0 ГиБ" in line, f"размер и память обязаны быть видны: {line}"


def test_cache_too_big_is_bad(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тот самый случай: 4 ГиБ кэша на 8 ГиБ машины - показ уронит машину."""
    _sets(monkeypatch, 4 * 1024**3)
    monkeypatch.setattr(doctor, "machine_memory", lambda: 8 * 1024**3)
    line, good = doctor._cache(_config())
    assert not good, "кэш вдвое тяжелее себя не влезает в 8 ГиБ - это «плохо», а не «ок»"
    assert "не влезает" in line, line


def test_cache_on_disk_weighs_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кэш на диске память не ест: тот же размер с UseDisk проходит."""
    _sets(monkeypatch, 4 * 1024**3, disk=True)
    monkeypatch.setattr(doctor, "machine_memory", lambda: 8 * 1024**3)
    line, good = doctor._cache(_config())
    assert good and "на диске" in line, line


def test_cache_unreadable_settings_do_not_fail_checkup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Молчащий TorrServer - это «внимание»: про него уже сказала строка выше."""
    monkeypatch.setattr(doctor, "_settings", lambda url: None)
    line, good = doctor._cache(_config())
    assert good and "неизвестен" in line, line


def _mdns_result(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    from torrcast import scan

    monkeypatch.setattr(scan, "by_mdns", lambda *_a, **_k: result)


def test_mdns_heard_receivers_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Эфир ответил: строка зелёная, и в ней имена - они и есть смысл mDNS."""
    from torrcast import scan

    _mdns_result(monkeypatch, scan.Mdns(devices=[scan.Device("10.0.0.50", name="Samsung Q70D")]))
    line, good = doctor._mdns()
    assert good and line.startswith("ок"), line
    assert "Samsung Q70D" in line


def test_mdns_missing_module_is_bad(monkeypatch: pytest.MonkeyPatch) -> None:
    """Нет zeroconf - это сломанная установка (системный python), а не свойство сети."""
    from torrcast import scan

    _mdns_result(monkeypatch, scan.Mdns(reason="module", note="mDNS не слушаю: нет zeroconf"))
    line, good = doctor._mdns()
    assert not good and line.startswith("плохо"), line
    assert "zeroconf" in line


def test_mdns_silence_is_a_warning_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тишина в эфире - «внимание»: адреса найдёт обход подсетей, теряются только имена."""
    from torrcast import scan

    _mdns_result(monkeypatch, scan.Mdns(reason="silence", note="mDNS слушал 4 сек - тишина"))
    line, good = doctor._mdns()
    assert good and line.startswith("внимание"), line
    assert "тишина" in line
