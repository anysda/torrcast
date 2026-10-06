"""Which file of a collection release is the asked picture; not sure - the largest stays.

«Дюна: Дилогия / 2021-2024» holds «Дюна 1.hdr.mkv» of 4.43 GiB and «Дюна 2.hdr.mkv» of
4.54: the largest file was the second film, and «Дюна» (2021) played «Часть вторая».
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.part_number import part_number
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile

#: The years a collection's name spans: «2021-2024», «1999 - 2003».
_SPAN_RE = re.compile(r"(?<!\d)((?:19|20)\d\d)\s*[-–]\s*((?:19|20)\d\d)(?!\d)")


def collection_part(picture: Picture, release: Release, files: list[TorrFile]) -> TorrFile | None:
    """The file of the picture in a collection, told by its year or as the first part.

    Two witnesses only, and either must point at ONE file:

    * the file's name carries the picture's year, and no other video file does;
    * the picture's year opens the span of the collection's name and does not close it:
      the picture is its first film, and that is the one file numbered 1, or the one
      unnumbered while the others are numbered from 2.

    Not a guess at a part from the picture's title: «Матрица: Перезагрузка» carries no
    number and is not the first film. A later film of a collection whose files name no
    years keeps the largest file, as does any release not marked a collection.
    """
    videos = [f for f in files if f.name.lower().endswith(VIDEO_EXT)]
    if not release.collection or len(videos) < 2 or picture.year is None:
        return None
    year = re.compile(rf"(?<!\d){picture.year}(?!\d)")
    dated = [f for f in videos if year.search(_stem(f))]
    if len(dated) == 1:
        return dated[0]
    span = _SPAN_RE.search(release.raw_name)
    if span is None or int(span[1]) != picture.year or int(span[2]) <= picture.year:
        return None
    numbers = {id(f): part_number(_stem(f)) for f in videos}
    first = [f for f in videos if numbers[id(f)] == 1]
    if not first:
        bare = [f for f in videos if numbers[id(f)] is None]
        if len(bare) == 1 and all((n or 0) >= 2 for n in numbers.values() if n is not None):
            first = bare
    return first[0] if len(first) == 1 else None


def _stem(file: TorrFile) -> str:
    """The file's own name without its folder and extension: «Дюна 1.hdr»."""
    return PurePosixPath(file.name).name.rsplit(".", 1)[0]


__all__ = ["collection_part"]
