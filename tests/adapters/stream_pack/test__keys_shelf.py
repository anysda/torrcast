"""Проверяет полку карт: адрес карты в кэше - ключом того файла, чью карту сняли."""

from pathlib import Path

import pytest

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache

URL = "http://127.0.0.1:8090/stream?link=0123456789abcdef&index=1"


def test_the_address_of_a_map_is_the_url_of_its_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ключ полки - сам URL: в нём hash раздачи и номер файла, то есть содержимое.

    Полка нужна не ради трафика (4 МБ), а ради времени: первое чтение хвоста стоит
    13.8 с на «Моане» 2016 и 24.4 с на «Моане 2».
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    where = _keys_cache(URL)
    assert where.parent == tmp_path / "keys"
    assert where.suffix == ".json"
    assert where == _keys_cache(URL), "один файл - один адрес"
    assert where != _keys_cache(URL.replace("index=1", "index=2")), "другой файл - другая карта"
