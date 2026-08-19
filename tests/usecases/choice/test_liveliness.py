"""Зеркало :mod:`torrcast.usecases.choice.liveliness`: насколько картина живая.

Мерок было три, и две отброшены на живой выдаче: сумма сидов вытягивает картину числом
раздач, а сиды верха ранжира не знают ни про потолок битрейта, ни про образы дисков.
Осталось честное - сиды лучшей раздачи, КОТОРОЙ КАРТИНА МОЖЕТ ИГРАТЬ.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, plan
from torrcast.usecases.choice.liveliness import liveliness


def test_the_weight_is_taken_from_the_liveliest_candidate_and_not_from_the_top_of_queue() -> None:
    """Считается лучшая ГОДНАЯ раздача, а не верх очереди: очередь сортируется не сидами.

    Замер «Мальтийского сокола» 1941 года: наверху очереди 5 сидов при 97 у годного
    соседа ниже, и картина с 22 раздачами весила меньше однораздачной тёзки 1931 года на
    16 сидов - дефолт садился на неё.
    """
    falcon = plan(pool=[film("верх очереди", seeders=5), film("сосед ниже", seeders=97)])

    assert liveliness(falcon) == 97


def test_a_release_the_picture_cannot_play_lends_it_no_weight_at_all() -> None:
    """Негодная раздача веса не даёт, сколько бы сидов на ней ни висело.

    41-гигабайтный 4K-ремукс «Тачек» выше потолка декодера: играть им картина не может,
    и вес по нему - обещание показа, которого не будет.
    """
    heavy = film("Кино 2020 BDRemux 2160p", seeders=200, size_gb=25.0, quality="2160p")
    cars = plan(pool=[heavy, film("честный 1080p", seeders=9)])

    assert liveliness(cars) == 9, "вес даёт только то, чем правда можно играть"
    assert liveliness(plan(pool=[heavy])) == 0, "годного нет вовсе - и веса нет"


def test_the_gates_are_asked_the_same_way_the_plan_itself_asks_them() -> None:
    """Ворота спрашиваются те же, что у плана: при открытых молчаливое имя весит.

    Пока ворота спрашивались строго, аниме с молчаливыми именами весило ноль целиком: у
    «наруто» дефолтом меню вместо сериала на 91 сид вставал полнометражный «Ниндзя в
    стране снега» на два.
    """
    silent = [film("Naruto.2002", seeders=91, codec=None, quality=None)]

    assert liveliness(plan(pool=silent)) == 0, "строгие ворота молчаливое имя не пускают"
    assert liveliness(plan(pool=silent, loose=True)) == 91


def test_the_last_hope_is_not_asked_here_and_hevc_stays_weightless() -> None:
    """🔴 Последняя надежда в вес НЕ входит: HEVC - носитель, а не предпочтение.

    Замер на кэше выдачи «синий экзорцист s1e1»: стоило дать HEVC вес, и дефолт меню
    переезжал с честного 1080p H.264 на одноимённую картину с HEVC, то есть ровно на то
    предпочтение, которого быть не должно.
    """
    hevc = plan(pool=[film("Кино 2020 BDRip HEVC 1080p", seeders=90, codec="HEVC")])

    assert liveliness(hevc) == 0
    assert liveliness(plan(pool=hevc.ranked, last_resort=True)) == 0, "ворота надежды не в счёт"
