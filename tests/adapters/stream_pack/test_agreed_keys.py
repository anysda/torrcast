"""Сверка карты с прогоном ложится на полку: следующий показ файла прогон не поднимает."""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable

from torrcast.adapters.stream_pack.agreed_keys import agreed_keys
from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.adapters.stream_pack.key_agreement import KeyAgreement
from torrcast.adapters.stream_pack.keys_agree import keys_agree
from torrcast.domain.film_keys import FilmKeys

URL = "http://торрент/поток?link=0123456789abcdef&index=0"

#: Ровный GOP в две секунды на минуту фильма.
KEYS = FilmKeys(60.0, [k * 2.0 for k in range(31)], [k * (2 << 20) for k in range(31)], "mkv")
SIZE = 120 << 20


class Pilot:
    """Подделка пробного прогона: отвечает названным вердиктом и считает запуски."""

    def __init__(self, verdict: bool) -> None:
        self.verdict, self.calls = verdict, 0

    def __call__(self, url: str, at: float, keys: FilmKeys) -> bool:
        self.calls += 1
        return self.verdict


def test_the_next_show_of_the_file_takes_the_agreed_map_from_the_shelf() -> None:
    """🔴 Показ - отдельный процесс: сверка прошлого показа не должна меряться снова."""
    first, second = Pilot(True), Pilot(True)

    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=first) is True
    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=second) is True

    assert (first.calls, second.calls) == (1, 0)


def test_another_boundary_or_another_map_asks_the_run_again() -> None:
    agreed_keys(URL, 20.0, KEYS, SIZE, agree=Pilot(True))
    moved, redrawn = Pilot(True), Pilot(True)
    shifted = FilmKeys(60.0, [k * 2.0 + 1.0 for k in range(30)], list(KEYS.offset[:30]), "mkv")

    agreed_keys(URL, 30.0, KEYS, SIZE, agree=moved)
    agreed_keys(URL, 20.0, shifted, SIZE, agree=redrawn)

    assert (moved.calls, redrawn.calls) == (1, 1)


def test_a_map_that_did_not_agree_is_not_trusted_next_time() -> None:
    first, second = Pilot(False), Pilot(True)

    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=first) is False
    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=second) is True

    assert second.calls == 1


def test_the_grid_of_a_show_asks_the_shelf_before_the_run() -> None:
    assert inspect.signature(grid_for).parameters["agree_of"].default is agreed_keys


def test_the_grid_hands_the_known_file_size_to_the_shelf() -> None:
    """Размер уже отдали метаданные раздачи: повторно спрашивать вход не нужно."""
    sizes: list[int] = []

    def agree(_url: str, _at: float, _keys: FilmKeys, size: int) -> bool:
        sizes.append(size)
        return True

    grid_for(
        URL,
        60.0,
        keys_of=lambda _url: KEYS,
        origin_of=lambda _url: 0.0,
        agree_of=agree,
        file_size=SIZE,
    )

    assert sizes == [SIZE], "размер файла потерялся до ключа полки"


def test_an_unmeasured_run_does_not_go_on_the_shelf() -> None:
    """🔴 Ровная граница не доказывает посадку: следующий показ обязан измериться заново."""
    first = Pilot(True)

    def unmeasured(*_args: object) -> KeyAgreement:
        return KeyAgreement(True, False)

    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=unmeasured) is True
    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=first) is True

    assert first.calls == 1, "неизмеренный прогон попал на полку и спрятал новый замер"


def test_a_map_that_only_matches_at_the_checked_boundary_is_not_from_the_shelf() -> None:
    """🔴 Сверка относится к карте целиком, а не только к первой совпавшей точке."""
    other_at = list(KEYS.at)
    other_at[3] = 6.5
    same_here = FilmKeys(60.0, other_at, KEYS.offset, "mkv")
    first, second = Pilot(True), Pilot(True)

    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=first) is True
    assert agreed_keys(URL, 20.0, same_here, SIZE, agree=second) is True

    assert second.calls == 1, "чужая карта прошла по совпадению одной границы"


def test_the_same_url_with_another_file_size_does_not_take_the_shelf() -> None:
    """Размер разделяет прямые ссылки и чужие адреса TorrServer с одинаковым URL."""
    first, second = Pilot(True), Pilot(True)

    assert agreed_keys(URL, 20.0, KEYS, SIZE, agree=first) is True
    assert agreed_keys(URL, 20.0, KEYS, SIZE + 1, agree=second) is True

    assert second.calls == 1, "размер файла не вошёл в ключ полки"


def test_a_pilot_without_a_first_packet_stays_off_the_shelf_through_the_real_verdict() -> None:
    """🔴 Стык, а не подделанный вердикт: ``nan`` прогона доходит до полки как «не мерили»."""
    mp4 = FilmKeys(KEYS.duration, KEYS.at, KEYS.offset, "mp4")
    runs: list[float] = []

    def run(stood: float) -> Callable[[str, float, FilmKeys], KeyAgreement]:
        def start(_url: str, at: float, _timeout: float) -> float:
            runs.append(at)
            return stood

        return lambda url, at, keys: keys_agree(url, at, keys, start=start)

    assert agreed_keys(URL, 20.0, mp4, SIZE, agree=run(math.nan)) is True
    assert agreed_keys(URL, 20.0, mp4, SIZE, agree=run(20.0)) is True

    assert runs == [20.0, 20.0], "неизмеренный прогон лёг на полку и спрятал новый замер"


def test_a_file_without_a_known_size_neither_reads_nor_writes_the_shelf() -> None:
    """Размера нет - нет и ключа: сверка идёт прогоном на каждом показе."""
    first, second = Pilot(True), Pilot(True)

    assert agreed_keys(URL, 20.0, KEYS, 0, agree=first) is True
    assert agreed_keys(URL, 20.0, KEYS, 0, agree=second) is True

    assert (first.calls, second.calls) == (1, 1), "полка поверила файлу без размера"
