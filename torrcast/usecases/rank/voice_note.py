"""Строка о том, из чего выбиралась озвучка; зовёт запуск показа."""

from __future__ import annotations

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.media import Media
from torrcast.usecases.rank.spoken import spoken
from torrcast.usecases.rank.spoken_kind import spoken_kind


def voice_note(media: Media, audio: int, native: bool = False) -> str:
    """Одна строка про то, из чего выбиралась озвучка: «дорожек rus 4, беру дубляж
    (LostFilm)»; выбора не было — пусто.

    Подпись взятой дорожки печатается и так, но она отвечает на вопрос «что играет», а
    не «почему это». У «Барби» рядом лежат три русские дорожки, и человек, услышав не ту,
    до сих пор не знал ни что выбор был, ни что рядом было из чего выбрать.

    🔴 TC-953. Считаются и называются дорожки на языке ЗРИТЕЛЯ - том самом, который
    ставит ярус лестницы (:func:`torrcast.domain.voice_order._tier`): оба читают один слот
    (:func:`torrcast.domain.catalogs.tongue.tongue`, а дефолт дорожки - ``spoken = language
    or tongue()`` в :meth:`torrcast.domain.media.Media.default_track`). Под английской
    ручкой «дорожек rus 2» было бы тем же враньём, что и «looking for a Russian dub» в
    строке фазы: продукт английскому зрителю русскую озвучку не ищет. Тег в строке -
    из каталога (:data:`rank.voice_tag`), а не второй копией в коде.

    Молчим ровно там, где выбирать было не из чего: одна дорожка на языке зрителя (или
    ни одной) - это не решение, а единственный вариант, и строка про него была бы шумом.
    Список студий целиком тут не печатается намеренно: он длинный, а нужен по запросу -
    ``cast voices <запрос>``.

    🔴 TC-242. Когда взятое расходится с лестницей по типу - двухголосый обошёл живой
    многоголосый - строка называет и ПРИЧИНУ, коротким хвостом: иначе человек читает её
    как противоречие лестнице. Причин таких две: студию судят по её отборной ступени
    (:attr:`torrcast.domain.audio_track.AudioTrack.rank_step`), а не по той, что произносится вслух.
    А у отечественной картины (``native``) выше всех переводов стоит её собственная
    дорожка: дубляж поверх русского оригинала - такая же потеря, как чужой дубляж поверх
    иностранного. Нет расхождения - нет и хвоста: счастливый путь не засоряем.
    """
    english = tongue() == EN

    def sought(track: AudioTrack) -> bool:
        """Дорожка на языке зрителя: английская под английской ручкой, иначе русская."""
        return track.is_english if english else track.is_russian

    count = sum(1 for t in media.tracks if sought(t))
    if count < 2 or not 0 <= audio < len(media.tracks):
        return ""
    track = media.tracks[audio]
    studio = track.studio
    # Собственная дорожка отечественной картины: русская и переводом себя не называет -
    # та же граница, что и в :func:`voice_order`.
    own = native and track.is_russian and not track.kind
    # Дорожек на языке зрителя две, а играет чужая - значит обе служебные; это тоже
    # выбор, и назвать его надо языком, а не видом перевода.
    what = (
        (
            phrase("rank.voice_original")
            if own
            else spoken_kind(track.kind) or phrase("rank.voice_ours")
        )
        if sought(track)
        else spoken(track)
    )
    tail = f" ({studio.name})" if studio and studio.name else ""
    why = ""
    if own:
        why = phrase("rank.voice_own_reason")
    elif sought(track) and studio and studio.ranks and track.rank_step < track.step:
        why = phrase("rank.voice_studio_tier", tier=studio.ranks)
    return phrase(
        "rank.voice_note",
        tag=phrase("rank.voice_tag"),
        count=count,
        what=what,
        tail=tail,
        why=why,
    )
