"""Проверяет хранилище, чей путь спрашивается на каждом обращении."""

from pathlib import Path

from torrcast.adapters.wiki.state_json_store import StateJsonStore


def test_different_state_directories_never_share_one_cache(tmp_path: Path) -> None:
    """Каталог состояния меняется на лету - и кэш обязан ехать за ним, а не за первым путём."""
    where = tmp_path / "first" / "facts.json"
    store = StateJsonStore(lambda: where)

    store.write({"Тачки|2006": {"rating": "IMDb 7.2"}})
    assert store.read() == {"Тачки|2006": {"rating": "IMDb 7.2"}}
    assert where.exists()

    where = tmp_path / "second" / "facts.json"
    assert store.read() == {}, "второй каталог чужой справки не видит"
    assert not where.exists(), "и чтение файла ему не заводит"
