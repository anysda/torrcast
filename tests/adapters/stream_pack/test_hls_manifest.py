"""Манифест VOD: весь фильм разом, длины кусков и обещание самостоятельных сегментов."""

from __future__ import annotations

import pytest

from torrcast.adapters.stream_pack.hls_manifest import hls_manifest


def test_the_manifest_describes_the_whole_film_and_says_it_has_ended() -> None:
    """У скользящего live-плейлиста длительности нет вовсе, и ТВ считал показ эфиром."""
    spans = [8.0, 8.0, 8.0, 4.0]

    text = hls_manifest(spans, 8, False)

    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in lines and "#EXT-X-TARGETDURATION:8" in lines
    assert lines[-1] == "#EXT-X-ENDLIST" and text.endswith("\n")
    assert "#EXT-X-INDEPENDENT-SEGMENTS" not in lines, "ровная сетка сама себя не обещает"
    written = [
        float(line[len("#EXTINF:") :].rstrip(",")) for line in lines if line[:8] == "#EXTINF:"
    ]
    assert written == spans and sum(written) == pytest.approx(28.0)
    assert [line for line in lines if line.endswith(".ts")] == [f"v{k}.ts" for k in range(4)]


def test_segments_on_keyframes_are_promised_to_be_independent() -> None:
    """Не украшение: приёмнику разрешено начать показ с любого куска - на этом перемотка."""
    assert "#EXT-X-INDEPENDENT-SEGMENTS" in hls_manifest([9.0, 12.0], 12, True)


def test_places_that_will_never_be_packed_are_marked_missing_instead_of_promised() -> None:
    """Продолжение с середины пакует только вперёд, а плейлист обещал и голову.

    Приёмник идёт за обещанным: замер на стенде («Интерстеллар», закладка 3600 с, слот
    335) - LOAD с ``current_time`` забирает ``v0`` ПЕРЕД своим куском. На холодном складе
    этот запрос висит выдержку и кончается 404, после которого ресивер не берёт LOAD
    минутами. Поэтому место, которого не будет, объявляется отсутствующим.

    Обещание длительности при этом не двигается ни на знак: те же ``EXTINF`` и те же
    имена, что и без дыр. Срежь тут голову вместо дыр - и ноль плейлиста уехал бы на
    место захода, а с ним и каждая секунда, которую приёмник называет показу.
    """
    spans = [8.0, 8.0, 8.0, 4.0]

    text = hls_manifest(spans, 8, False, gaps=(0, 2))
    lines = text.splitlines()

    assert "#EXT-X-VERSION:8" in lines, "тег дыры живёт с восьмой версии"
    assert "#EXT-X-VERSION:3" in hls_manifest(spans, 8, False), "без дыр версия не двигается"
    assert lines[lines.index("v0.ts") - 2] == "#EXT-X-GAP"
    assert lines[lines.index("v2.ts") - 2] == "#EXT-X-GAP"
    assert lines[lines.index("v1.ts") - 2] != "#EXT-X-GAP", "это место есть, его обещают"
    assert lines.count("#EXT-X-GAP") == 2, "дыра только там, где названа"
    written = [
        float(line[len("#EXTINF:") :].rstrip(",")) for line in lines if line[:8] == "#EXTINF:"
    ]
    assert written == spans, "длительность показа дыры не трогают"
    assert [line for line in lines if line.endswith(".ts")] == [f"v{k}.ts" for k in range(4)]
    assert lines[-1] == "#EXT-X-ENDLIST"
