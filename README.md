# torrcast

Консольная утилита `cast`: находит фильм или сериал по названию (понимая франшизы
и кривые запросы), даёт выбрать релиз и озвучку и стримит торрент на ТВ через
Chromecast — **без скачивания и без облака в пути данных**. Поток не покидает LAN.

Идейный наследник kinocast, но каталог — торрент-трекеры.

## Установка

Три действия, ноль регистраций и внешних API-ключей:

```sh
git clone git@192.168.1.25:anysda/torrcast.git && cd torrcast
./install.sh                      # зависимости, TorrServer, Prowlarr, юниты
cast --tv 192.168.100.102         # единственная настройка — адрес ТВ
```

Все внутренние ключи (Prowlarr↔cast) `install.sh` генерит сам.

## Команды

```
cast <запрос> [sNeM] [--new] [--release N] [--audio N] [--dry]
cast stop      # снять каст, зафиксировать позицию
cast status    # что играет, позиция/длительность, источник
```

Пауза и перемотка — пультом ТВ. Коды выхода: `0` ок · `1` не нашли ·
`2` инфра-ошибка (Prowlarr / TorrServer / приёмник).

## Как устроено

```
запрос → search (Prowlarr/Torznab) → parse (имена раздач, франшизы, sNeM)
       → stream (TorrServer, кэш в RAM) → ffmpeg → HLS → cast (Chromecast)
```

Шесть модулей пакета `torrcast`: `cli` · `parse` · `search` · `stream` · `cast` ·
`state`. Полное ТЗ — [SPEC.md](SPEC.md).

Постоянных демонов своих нет: на время показа `cast` поднимает transient-юнит
`torrcast-play` (ffmpeg + раздача HLS по http на голом IP + сторож позиции; адрес
берётся с той ноги, которой стенд смотрит на ТВ, так что DNS в пути показа нет).
Команда завершилась —
показ продолжается, логи в journald (`journalctl -u torrcast-play`), `cast stop`
гасит юнит и фиксирует позицию. Прогресс живёт в `/var/lib/torrcast/state.json`:
позиция ≥ 95 % длительности = досмотрено.

## Разработка

```sh
uv sync                 # venv на Python 3.12 + dev-зависимости
uv run ruff check .
uv run mypy
uv run pytest
```

> ⚠️ На agent-ops команда `cast` уже занята kinocast. Entry-point torrcast живёт
> только внутри venv проекта; системный алиас не трогаем.
