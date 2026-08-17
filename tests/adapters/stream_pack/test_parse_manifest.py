"""Проверяет разбор манифеста: пары «сегмент - длительность» и признак конца ленты."""

from torrcast.adapters.stream_pack.parse_manifest import parse_manifest

MANIFEST = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:15
#EXT-X-INDEPENDENT-SEGMENTS
#EXTINF:9.927000,
v0.ts
#EXTINF:14.890000,
v1.ts
#EXT-X-ENDLIST
"""


def test_each_segment_keeps_the_duration_written_above_it() -> None:
    """Куски разной длины (6.0-14.9 с на живом релизе), и длительность у каждого своя.

    Взять один шаг на всех значило бы соврать про место фильма: сетка стоит на опорных
    кадрах, а не на ровных отсчётах.
    """
    segments, ended = parse_manifest(MANIFEST)
    assert segments == [("v0.ts", 9.927), ("v1.ts", 14.89)]
    assert ended is True


def test_a_playlist_without_the_end_is_not_finished() -> None:
    """Без ``ENDLIST`` лента ещё пишется, и читатель обязан это видеть."""
    segments, ended = parse_manifest("#EXTM3U\n#EXTINF:10.0,\nv0.ts\n")
    assert segments == [("v0.ts", 10.0)] and ended is False


def test_a_broken_duration_does_not_drop_the_segment() -> None:
    """Битая строка ``EXTINF`` не выбрасывает кусок: имя куска важнее его длительности."""
    segments, _ = parse_manifest("#EXTM3U\n#EXTINF:совсем не число,\nv7.ts\n")
    assert segments == [("v7.ts", 0.0)]
