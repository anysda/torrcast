"""Строка о том, из чего выбиралась озвучка; зовёт запуск показа."""

from __future__ import annotations

from torrcast.domain.media import Media
from torrcast.usecases.rank.spoken import spoken


def voice_note(media: Media, audio: int, native: bool = False) -> str:
    """Одна строка про то, из чего выбиралась озвучка: «дорожек rus 4, беру дубляж
    (LostFilm)»; выбора не было — пусто.

    Подпись взятой дорожки печатается и так, но она отвечает на вопрос «что играет», а
    не «почему это». У «Барби» рядом лежат три русские дорожки, и человек, услышав не ту,
    до сих пор не знал ни что выбор был, ни что рядом было из чего выбрать.

    Молчим ровно там, где выбирать было не из чего: одна русская дорожка (или ни одной) -
    это не решение, а единственный вариант, и строка про него была бы шумом. Список
    студий целиком тут не печатается намеренно: он длинный, а нужен по запросу -
    ``cast voices <запрос>``.

    🔴 TC-242. Когда взятое расходится с лестницей по типу - двухголосый обошёл живой
    многоголосый - строка называет и ПРИЧИНУ, коротким хвостом: иначе человек читает её
    как противоречие лестнице. Причин таких две: студию судят по её отборной ступени
    (:attr:`torrcast.domain.audio_track.AudioTrack.rank_step`), а не по той, что произносится вслух.
    А у отечественной картины (``native``) выше всех переводов стоит её собственная
    дорожка: дубляж поверх русского оригинала - такая же потеря, как чужой дубляж поверх
    иностранного. Нет расхождения - нет и хвоста: счастливый путь не засоряем.
    """
    russian = sum(1 for t in media.tracks if t.is_russian)
    if russian < 2 or not 0 <= audio < len(media.tracks):
        return ""
    track = media.tracks[audio]
    studio = track.studio
    # Собственная дорожка отечественной картины: русская и переводом себя не называет -
    # та же граница, что и в :func:`voice_order`.
    own = native and track.is_russian and not track.kind
    # Русских две, а играет нерусская - значит обе служебные; это тоже выбор, и назвать
    # его надо языком, а не видом перевода.
    what = (
        ("оригинальную" if own else track.kind or "русскую") if track.is_russian else spoken(track)
    )
    tail = f" ({studio.name})" if studio and studio.name else ""
    why = ""
    if own:
        why = " - картина снята по-русски, это её собственная дорожка"
    elif track.is_russian and studio and studio.ranks and track.rank_step < track.step:
        why = f" - эта студия у нас на уровне «{studio.ranks}»"
    return f"дорожек rus {russian}, беру {what}{tail}{why}"
