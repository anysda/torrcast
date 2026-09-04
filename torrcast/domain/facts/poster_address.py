"""Адрес картинки из ответа ``imageinfo``; зовёт адаптер постера."""

from __future__ import annotations

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def poster_address(payload: JsonValue) -> str:
    """Ответ ``imageinfo`` → адрес файла; сначала уменьшенная копия, потом оригинал.

    Уменьшенная копия стоит первой не ради трафика, а ради самой картинки: постеры
    бывают векторными (у «Уэнздей» в инфобоксе логотип ``.svg``), а карточка плеера
    вектор не рисует - ``iiurlwidth`` отдаёт его растром. Оригинал остаётся запасным
    ответом: у него тот же формат, что лежит на складе, и ужимать его некому.

    🔴 Лежачая картинка адресом не становится вовсе. В инфобоксе у сериалов и антологий
    вместо обложки сплошь и рядом лежит вордмарк - надпись с названием на тёмном фоне: у
    «Аниматрицы» это ``Theanimatrix-logo.svg`` 512x147, у «Уэнздей» - логотип 1200x312.
    Карточка плеера рисует такой картинкой широкую тёмную полосу, по которой картину не
    узнать. Отказ выносится ЗДЕСЬ, до загрузки байтов, а не после: приговор и байты
    обязаны отвечать об одном, и молчание про лежачий файл честно пускает дальше
    следующего кандидата - русскую обложку той же картины, а нет и её, так IMDb.
    """
    query = json_map(json_map(payload).get("query"))
    for page in json_rows(query.get("pages")):
        for info in json_rows(json_map(page).get("imageinfo")):
            row = json_map(info)
            if _lying_down(row):
                continue
            address = str(row.get("thumburl") or row.get("url") or "")
            if address:
                return address
    return ""


def _lying_down(row: dict[str, JsonValue]) -> bool:
    """Шире, чем выше, - значит вордмарк или кадр, но не постер.

    Меряется уменьшенная копия, а не оригинал: именно её адрес и уезжает в карточку.
    Пропорцию ``iiurlwidth`` не искажает, так что судить по любой из пар можно одинаково.

    🔴 Неизвестный размер значит «пропустить», а не «отказать». Стороны приезжают полями
    ответа, и откажи мы по их отсутствию - смена формата ответа Википедии оставила бы без
    постеров ВСЕ картины разом, а выглядело бы это как честное «постера не нашлось».
    Квадрат проходит: лежачесть - это строгое превышение, а не «не выше».
    """
    for across, down in (("thumbwidth", "thumbheight"), ("width", "height")):
        wide, high = _side(row.get(across)), _side(row.get(down))
        if wide and high:
            return wide > high
    return False


def _side(value: JsonValue) -> int:
    """Сторона картинки числом; поля нет или там не число - ноль."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
