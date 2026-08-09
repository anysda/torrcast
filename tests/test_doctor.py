"""``cast doctor``: вес метапоиска в вердикте.

Каталог держится на одном метапоисковом индексере: прямые трекеры его не перекрывают.
Поиск без него работает, поэтому вердикт остаётся проходным - но строка про неполную
выдачу обязана быть, иначе урезанный каталог выглядит как поиск без причины.
"""

from __future__ import annotations

import subprocess
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
    monkeypatch.setattr(doctor, "_probe_indexer", lambda config, indexer: True)


def _lines(monkeypatch: pytest.MonkeyPatch, indexers: object) -> list[tuple[str, bool]]:
    _answers(monkeypatch, indexers)
    return list(doctor._prowlarr(_config()))


def _entry(name: str, enable: bool = True) -> dict[str, Any]:
    return {"name": name, "enable": enable}


def test_live_probe_and_backoff_expose_a_dead_indexer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Флаг enable не здоровье: пауза и пустая живая проба обе делают doctor красным."""
    indexers = [{"id": 7, "name": KEY_INDEXER, "enable": True}]

    def fake(url: str, headers: dict[str, str]) -> object | None:
        if url.endswith("/api/v1/indexer"):
            return indexers
        if url.endswith("/api/v1/indexerstatus"):
            return [{"indexerId": 7, "disabledTill": "2026-08-09T12:30:00Z"}]
        return []

    monkeypatch.setattr(doctor, "_json", fake)
    monkeypatch.setattr(doctor, "_probe_indexer", lambda config, indexer: False, raising=False)

    lines = list(doctor._prowlarr(_config()))
    text = "\n".join(line for line, _ in lines)
    assert "индексер Knaben отключён Prowlarr до 2026-08-09 12:30:00" in text
    assert "индексер Knaben не ответил на живой поиск - выдача неполная" in text
    assert any(not good for _, good in lines)


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


def _sets(
    monkeypatch: pytest.MonkeyPatch, size: int, disk: bool = False, path: str = "/var/cache"
) -> None:
    monkeypatch.setattr(
        doctor,
        "_settings",
        lambda url: {
            "CacheSize": size,
            "UseDisk": disk,
            "TorrentsSavePath": path if disk else "",
        },
    )


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


def test_cache_on_disk_is_not_measured_by_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Замер: кэш на диске стоит службе сотню мегабайт при любом своём размере.

    Поэтому 12 ГиБ кэша на 8-гигабайтной машине - это «ок», хотя в памяти столько не
    бывает вовсе. Проверяем именно это: память тут больше не мера.
    """
    _sets(monkeypatch, 12 * 1024**3, disk=True)
    monkeypatch.setattr(doctor, "machine_memory", lambda: 8 * 1024**3)
    monkeypatch.setattr(doctor, "disk_free", lambda path: 60 * 1024**3)
    line, good = doctor._cache(_config())
    assert good, f"12 ГиБ на диске при 8 ГиБ памяти - это норма, а не поломка: {line}"
    assert "на диске" in line and "12.0 ГиБ" in line, line


def test_cache_on_disk_without_room_for_warmup_is_bad(monkeypatch: pytest.MonkeyPatch) -> None:
    """Раздел, где кэшу место есть, а прогреву уже нет, - это «плохо».

    Обещание «показ переживает обрыв» держат оба сразу, и кэш, съевший раздел, ломает
    его ровно так же, как отсутствие кэша.
    """
    _sets(monkeypatch, 4 * 1024**3, disk=True)
    monkeypatch.setattr(doctor, "disk_free", lambda path: 10 * 1024**3)
    line, good = doctor._cache(_config())
    assert not good, f"10 ГиБ на раздел под кэш и прогрев - этого не хватает: {line}"
    assert "прогреву места не остаётся" in line, line


def test_cache_on_disk_without_path_is_bad(monkeypatch: pytest.MonkeyPatch) -> None:
    """UseDisk без пути - служба кладёт кэш куда сама решит, и это не наш раздел."""
    _sets(monkeypatch, 4 * 1024**3, disk=True, path="")
    line, good = doctor._cache(_config())
    assert not good and "путь не задан" in line, line


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


def _unit_env(monkeypatch: pytest.MonkeyPatch, environment: str) -> tuple[str, bool]:
    """Строка про дорогу к трекерам при таком окружении юнита Prowlarr - без systemd."""

    class _Done:
        stdout = environment

    # Через сам модуль subprocess, а не через реэкспорт из doctor: mypy strict
    # справедливо не считает чужой импорт частью договора модуля.
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Done())
    return doctor._family()


def test_дорога_prowlarr_к_трекерам_видна_человеку(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 TC-311. IPv6 - это не «медленнее», это молчащий индексер.

    Замер тем же мгновением и тем же запросом: по IPv6 тело трекера встаёт раньше, чем
    по IPv4 (13.4-13.9 КБ против 17.5-18.9 КБ у одного имени, 15.0-16.4 против 20.5 у
    другого, шесть попыток из шести), а по умолчанию Prowlarr берёт именно IPv6. Проба
    при этом отвечает «здоров», потому что щупает не ту дорогу, - вот об этом и строка.
    """
    sick, _ = _unit_env(monkeypatch, "Environment=LANG=ru_RU.UTF-8\n")
    good, _ = _unit_env(monkeypatch, f"Environment=LANG=ru_RU.UTF-8 {doctor.IPV4_ONLY}\n")
    print(f"{sick}\n{good}")
    assert sick.startswith("внимание"), "может уйти на IPv6 - человек обязан об этом услышать"
    assert doctor.IPV4_ONLY in sick, "у строки должно быть лечение, а не только диагноз"
    assert good.startswith("ок"), "ручка на месте - дорога известна"
