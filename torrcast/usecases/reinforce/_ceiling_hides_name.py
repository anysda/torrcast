"""Повод второго круга: выдача упёрлась в потолок индексера, а картины в ней нет."""

from __future__ import annotations

from torrcast.domain.catalog_has_name import catalog_has_name
from torrcast.domain.picture import Picture
from torrcast.ports.torrent_catalogue import IndexerClient


def _ceiling_hides_name(
    client: IndexerClient, name: str, pictures: list[Picture], found: list[Picture]
) -> bool:
    """Выдача упёрлась в потолок индексера, а картины с именем запроса в ней нет.

    Третий повод второго круга рядом с тощим и негодным пулом
    (:func:`worth_asking_original`): пул густой и годный, но обрезан СВЕРХУ. Замер по
    сохранённым выдачам: 46 запросов из 100 хотя бы один индексер закрыл ровно сотней
    строк (у RuTor это его собственный потолок - с ``limit=400`` он отдаёт те же 100).
    Пока имя запроса в выдаче есть, обрезан хвост - досадно, но жить можно. А вот когда
    имени нет вовсе, потолок прячет САМУ картину: по запросу «девять» 21 раздача картины
    «Девять» (2009) лежит за сотней, каталог её не видит, и в меню человек получает
    «Девять ярдов» - при том что пул тощим не считается и ни один добор не запускается.

    Пустой ``found`` сюда не доходит: там пул тощий по определению, и первым отвечает
    добор вторым языком (:func:`_second_language`).
    """
    return (
        bool(found) and bool(getattr(client, "capped", ())) and not catalog_has_name(name, pictures)
    )
