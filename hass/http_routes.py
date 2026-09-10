"""Адреса и границы HTTP-моста, общие для сервера и разбора запросов."""

from __future__ import annotations

from hass.bridge import VOLUME
from hass.say import SEEKBY, TOGGLE
from hass.stopping import STOP

#: Слушаем все интерфейсы: Home Assistant приходит из локальной сети, а не с петли.
ANY_INTERFACE = "0.0.0.0"
#: Порт моста. Занят он бывает только другим таким же мостом.
PORT = 8479
#: Потолок тела запроса: команды тут короткие, а читать чужой гигабайт мы не обязаны.
BODY_LIMIT = 64 * 1024
STATE, PLAY, CONTROL, NEXT = "/api/state", "/api/play", "/api/control", "/api/next"
SEARCH = "/api/search"
#: Показ без запроса вовсе - то же самое, что пустой ``cast``. Отдельным маршрутом, а не
#: пустым ``query`` у :data:`PLAY`: тому, кто просит показ ПО ЗАПРОСУ, пустой запрос
#: по-прежнему брак, и отказ ``no_query`` за ним остаётся.
RESUME = "/api/resume"
#: Картинку играющей картины раздаёт САМ серв: Home Assistant за ней наружу не ходит,
#: иначе её тянул бы клиент через сеть, где режут по SNI (:mod:`hass.posters`).
POSTER = "/api/poster/"
#: Команды пульта, которым число обязательно (``seekby`` - секунды со знаком).
NEEDS_ARG = (SEEKBY, VOLUME)
#: Слова, которые принимает ``POST /api/control``.
COMMANDS = (TOGGLE, SEEKBY, VOLUME, STOP)
