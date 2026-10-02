"""Проверяет полку сверок входа: сверка прогрева доезжает до показа без ffmpeg."""

from __future__ import annotations

import json

import pytest

from torrcast.adapters.stream_pack.entry_clean import _entry_cache, entry_clean

URL = "http://торрент/поток?link=0123456789abcdef&index=0"


class Check:
    """Подделка сверки входа: отвечает названным приговором и считает вызовы."""

    def __init__(self, clean: bool | None) -> None:
        self.clean, self.calls = clean, 0

    def __call__(self, url: str, seek: float) -> bool | None:
        self.calls += 1
        return self.clean


def test_the_show_takes_the_entry_checked_by_the_warm_up_from_the_shelf() -> None:
    """🔴 Прогрев записи - другой процесс: показ не должен сверять то же место снова."""
    assert entry_clean(URL, 5000.0, check=Check(False)) is False
    show = Check(True)
    assert entry_clean(URL, 5000.0, check=show) is False
    assert show.calls == 0, "показ сверил вход, хотя ответ лежал на полке"


def test_another_place_of_the_same_file_is_checked_again() -> None:
    """Чистота входа - свойство места: у x264 с open-gop соседний вход несёт MMCO."""
    entry_clean(URL, 5000.0, check=Check(False))
    show = Check(True)
    assert entry_clean(URL, 4990.694, check=show) is True
    assert show.calls == 1


def test_an_entry_that_was_not_checked_is_not_put_on_the_shelf() -> None:
    """Не сверили - это не приговор: следующий спрос обязан сверить, а не взять набивку."""
    entry_clean(URL, 5000.0, check=Check(None))
    show = Check(False)
    assert entry_clean(URL, 5000.0, check=show) is False
    assert show.calls == 1


@pytest.mark.parametrize(
    "body",
    ["{не json", json.dumps({"source": "http://чужой/поток", "seek": 5000.0, "clean": False}),
     json.dumps({"source": URL, "seek": 5000.0, "clean": "нет"}),
     json.dumps({"source": URL, "seek": 5000.0})],
    ids=["битая", "чужая", "не да-нет", "без приговора"],
)  # fmt: skip
def test_a_broken_or_foreign_record_is_a_miss(body: str) -> None:
    """Неверный приговор стоит мёртвого показа или лишнего перекода: сомнительное - промах."""
    cache = _entry_cache(URL)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(body, "utf-8")
    show = Check(True)
    assert entry_clean(URL, 5000.0, check=show) is True
    assert show.calls == 1
