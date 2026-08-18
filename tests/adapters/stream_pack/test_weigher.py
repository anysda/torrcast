"""Проверяет предсказатель веса куска: по карте, по нашему битрейту и без карты вовсе."""

from torrcast.adapters.stream_pack.weigher import weigher

#: Ровная карта: опорный кадр каждые две секунды, ровно мегабайт между соседними.
KEYS = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
SIZES = [k << 20 for k in range(len(KEYS))]


def test_the_weight_comes_from_the_map_of_the_container() -> None:
    """Карта даёт байты контейнера, и вес куска - разность смещений его границ."""
    weigh = weigher(KEYS, SIZES, 0.0, 0.0)
    assert weigh(0.0, 4.0) == 2 << 20
    assert weigh(2.0, 10.0) == 4 << 20
    assert weigh(4.0, 4.0) == 0.0, "нулевой кусок ничего не весит"


def test_what_does_not_travel_to_the_tv_is_subtracted() -> None:
    """У релиза десять озвучек и восемь субтитров сверх картинки, а уезжает видео плюс наш AAC.

    Не вычти их - и потолок веса резал бы сетку по весу того, чего приёмник не увидит.
    """
    container = weigher(KEYS, SIZES, 0.0, 0.0)(0.0, 4.0)
    lighter = weigher(KEYS, SIZES, 1.0, 0.0)(0.0, 4.0)
    assert lighter < container
    assert lighter == container - 1.0 * 4.0 * 1e6 / 8


def test_a_heavy_piece_does_not_travel_heavier_than_the_recode_ceiling() -> None:
    """Тяжёлый кусок уезжает перекодом, и выше потолка ему не уехать при всём желании."""
    ceiling = 1.0
    assert weigher(KEYS, SIZES, 0.0, ceiling)(0.0, 4.0) == ceiling * 4.0 * 1e6 / 8


def test_our_own_bitrate_does_not_ask_the_map_at_all() -> None:
    """🔴 Сплошной перекод: вес задаём мы сами, и вес источника к нему отношения не имеет.

    Замер на живом Q70D («Bocchi the Rock», 1.3 Мбит/с HEVC): сетка поверила карте,
    поставила куски по 15-20 с, а перекод положил в них 18.3 и 21.4 МБ при потолке 16.
    """
    fixed = weigher(KEYS, SIZES, 5.0, 5.0, fixed_mbit=2.0)
    assert fixed(0.0, 10.0) == 2.0 * 10.0 * 1e6 / 8
    assert weigher([], [], 0.0, 0.0, fixed_mbit=2.0)(0.0, 10.0) == 2.0 * 10.0 * 1e6 / 8


def test_without_a_map_the_weight_is_honestly_unknown() -> None:
    """Карты смещений нет - предсказатель отдаёт ноль, и правило потолка не срабатывает.

    Соврать тут опаснее, чем промолчать: выдуманный вес порезал бы сетку не там.
    """
    assert weigher(KEYS, [], 0.0, 0.0)(0.0, 4.0) == 0.0
    assert weigher(KEYS, SIZES[:2], 0.0, 0.0)(0.0, 4.0) == 0.0
    assert weigher([0.0], [0], 0.0, 0.0)(0.0, 4.0) == 0.0
