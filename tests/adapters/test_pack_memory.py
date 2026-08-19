"""Проверяет, что замеры упаковщика помнит один объект на процесс, а не копия на модуль."""

from torrcast.adapters import pack_memory
from torrcast.adapters.stream_pack.pack_origin import pack_origin

#: Ключ памяти - URL потока: в нём hash раздачи и номер файла, как у полки карт.
URL = "http://torrserver.invalid/stream?link=0123456789abcdef&index=0"


def test_the_packer_takes_the_origin_of_the_tape_from_this_memory() -> None:
    """Положенное сюда начало ленты упаковщик берёт готовым, а не меряет заново.

    Сдвиг считается РАЗ на файл и обязан быть ОДИН на все заходы - живой упаковки,
    прогрева, перекода. Разъедься эта память с упаковщиком, и заход из середины встал бы
    на другой ленте, чем заход от нуля: на их стыке метки пошли бы назад.
    """
    try:
        pack_memory._ORIGIN[URL] = 0.125
        assert pack_origin(URL) == 0.125, "упаковщик не увидел готовый замер начала ленты"
    finally:
        pack_memory._ORIGIN.pop(URL, None)


def test_each_dictionary_of_this_memory_is_guarded_by_its_own_lock() -> None:
    """Замки у полок разные: они стерегут разные словари.

    Один замок на две полки связал бы замер начала ленты с доверием карте кадров:
    нитка, меряющая начало, держала бы и тех, кому нужна только карта.
    """
    assert pack_memory._SEEK_LOCK is not pack_memory._ORIGIN_LOCK
