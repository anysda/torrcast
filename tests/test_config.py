"""Проверки закрытого файла настройки Telegram."""

from pathlib import Path

from pytest import MonkeyPatch

from tgbot.config import CONFIG_ENV, Config


def test_path_is_overridden_and_saved_with_mode_0600(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    path = tmp_path / "telegram.json"
    monkeypatch.setenv(CONFIG_ENV, str(path))
    Config("token", "-100", "http://proxy:80").save()
    assert Config.load() == Config("token", "-100", "http://proxy:80")
    assert path.stat().st_mode & 0o777 == 0o600
    assert Config.remove()
    assert not path.exists()
