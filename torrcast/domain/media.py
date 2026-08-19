"""Описывает паспорт медиафайла для отбора и показа."""

from dataclasses import dataclass

from torrcast.domain._media_picture import _MediaPicture
from torrcast.domain.delivered_mbit import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.voice_order import voice_order

__all__ = ["AUDIO_MBIT", "TS_OVERHEAD", "Media"]


@dataclass(frozen=True, slots=True)
class Media(_MediaPicture):
    """Паспорт медиафайла целиком; тут - что он говорит о ЗВУКЕ и его выборе."""

    @property
    def foreign(self) -> bool:
        """Паспорт ПРЯМО говорит, что русской дорожки в файле нет.

        🔴 TC-178. «Включилось» значит «включилось с русской озвучкой», и решает это не
        имя раздачи, а паспорт: релиз, у которого русской дорожки не оказалось, отбор
        бракует и идёт дальше по очереди
        (:meth:`torrcast.usecases.select_bench.bench.Bench.resolve`).

        Слово «прямо» тут несёт всю нагрузку. Правда - это ``rus`` рядом с ``jpn``, а
        неправда бывает двух сортов, и обе стоят зрителю картины:

        * дорожек нет вовсе (паспорт прочитан наполовину, ``ffprobe`` отдал одно видео) -
          сказать про язык нечего, и бракуем мы тут не релиз, а собственное незнание;
        * язык дорожки не назван (``und``, :attr:`AudioTrack.named`) - а таких раздач на
          рутрекере полно, и русская дорожка внутри них самая обычная. Достаточно ОДНОЙ
          безымянной дорожки, чтобы паспорт замолчал: судить её нечем, и выкидывать
          картину по догадке нельзя.

        Заголовок при этом не игнорируется: у безымянной дорожки его читает
        :attr:`AudioTrack.is_russian` (знакомая студия, «Дубляж»), и такая дорожка
        считается русской без всякого тега.
        """
        if not self.tracks or any(track.is_russian for track in self.tracks):
            return False
        return all(track.named for track in self.tracks)

    @property
    def russian(self) -> bool:
        """Паспорт ПРЯМО говорит, что русская дорожка в файле есть.

        Не отрицание :attr:`foreign`, и путать их нельзя: у паспорта три ответа, а не два.
        «Да» - вот эта строка, «нет» - :attr:`foreign`, а всё, что осталось между ними, -
        НЕЗНАНИЕ: дорожка без тега языка, про которую ни ffprobe, ни заголовок ничего не
        сказали. Отбор относится к незнанию не так, как к «нет»
        (:func:`torrcast.usecases.rank.voice_unproven.voice_unproven`):
        отказывать по догадке нельзя, а спросить соседа, чьё имя русскую прямо обещает,
        - можно и стоит.
        """
        return any(track.is_russian for track in self.tracks)

    def default_track(self) -> int:
        """«Самая нормальная» озвучка — та, что играет без вопросов: русский дубляж →
        русский многоголосый → прочий русский → оригинал → чужой дубляж; служебные
        дорожки (тифлокомментарий, комментарии) — в самый низ. Выбор не молчаливый:
        подпись дорожки печатается в строке запуска.
        """
        if not self.tracks:
            return 0
        return min(self.tracks, key=voice_order).index

    def find_voice(self, label: str) -> int | None:
        """Дорожка с такой подписью (память озвучки); ``None`` — такой нет.

        Сравниваем подписи, а не номера: релиз мог смениться, и «дорожка 4» в новом
        релизе — это другая студия. Подпись же (`rus · MVO (LostFilm)`) переживает смену
        релиза ровно тогда, когда та же озвучка в нём есть.
        """
        want = label.casefold().strip()
        if not want:
            return None
        return next((t.index for t in self.tracks if t.label.casefold().strip() == want), None)
