"""Сторож на вето видео-приметы у :mod:`torrcast.domain.nonvideo_release`.

Вето - несущая часть правила N1-N4, а не оптимизация: без него слово `MP3` или
`REPACK` в сцен-имени настоящего фильма отсеивало бы его как не-видео. Кто «упростит»
условие и снимет проверку видео-приметы первой - здесь обязан покраснеть.

Вето читает имя тем же алфавитом, что и приметы не-видео: `4К`, `ВDRip`, `НЕVC` с
кириллическими двойниками (на корпусе-100 их 60 штук) обязаны давать вето, иначе
расширение примет не-видео заводит новый способ убить настоящий фильм.
"""

from torrcast.domain.nonvideo_release import _is_nonvideo_release


def test_a_real_film_with_an_mp3_track_is_not_nonvideo() -> None:
    assert not _is_nonvideo_release(
        "Индиана Джонс и Часы Судьбы ... ProRes 444 10-bit encode, MP3 RUS Dub 2.0/DTS-HD/AC-3 5.1"
    )


def test_a_repack_is_not_nonvideo() -> None:
    assert not _is_nonvideo_release("Oppenheimer 2023 REPACK 1080p BluRay DD 5 1 x264-PTer")


def test_a_cyrillic_video_mark_still_vetoes() -> None:
    assert not _is_nonvideo_release("Матрица / The Matrix (1999) ВDRip, MP3 RUS Dub")
    assert not _is_nonvideo_release("Аватар / Avatar (2009) 4К, FLAC 5.1")
    assert not _is_nonvideo_release("Джанго освобождённый (2012) НЕVC, MP3")
    assert not _is_nonvideo_release("Игра престолов (2011) 1080р, MP3 5.1")
