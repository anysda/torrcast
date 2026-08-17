"""Проверяет сборку magnet: хэш, имя и публичные ретрекеры."""

from torrcast.adapters.prowlarr.magnet_for import PUBLIC_TRACKERS, magnet_for


def test_magnet_has_hash_name_and_trackers() -> None:
    """``magnetUrl`` у Prowlarr - прокси-ссылка, поэтому magnet собираем сами."""
    magnet = magnet_for("ABCdef0123456789ABCDEF0123456789abcdef01", "Тачки 3")
    assert magnet.startswith("magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01")
    assert "dn=%D0%A2%D0%B0%D1%87%D0%BA%D0%B8%203" in magnet
    assert magnet.count("&tr=") == len(PUBLIC_TRACKERS)


def test_magnet_without_title_has_no_dn() -> None:
    assert "dn=" not in magnet_for("0" * 40)


def test_адреса_трекеров_кодируются_целиком() -> None:
    """Без экранирования двоеточий и слэшей часть адреса ушла бы в соседний параметр."""
    magnet = magnet_for("0" * 40)
    assert "tr=udp%3A%2F%2F" in magnet
    assert "tr=udp://" not in magnet
