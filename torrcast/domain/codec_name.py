"""Формирует человекочитаемое имя видеокодека."""

from torrcast.domain.catalogs.phrase import phrase

COPY_DEPTH = 8


def codec_name(codec: str, depth: int = 0) -> str:
    """Как называть картинку человеку: ``h264``, ``h264 10 бит``, ``hevc``.

    Только для строк - в решениях у имени работы нет (:func:`recodes_whole`). Но врать в
    них нельзя: два потока, из которых один приёмник играет часами, а на другом встаёт
    намертво, зовутся в паспорте одинаково - значит, называть их одинаково нельзя нам.
    """
    if not codec:
        return ""
    return phrase("stream.codec_bits", codec=codec, depth=depth) if depth > COPY_DEPTH else codec
