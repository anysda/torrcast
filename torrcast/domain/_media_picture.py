"""Что паспорт говорит о КАРТИНКЕ: ступень качества, глубина цвета, вес и HDR.

Наследует их :class:`torrcast.domain.media.Media`, и только он.
"""

from dataclasses import dataclass

from torrcast.domain._media_facts import _MediaFacts
from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.codec_name import codec_name
from torrcast.domain.color_depth import color_depth
from torrcast.domain.delivered_mbit import delivered_mbit
from torrcast.domain.recodes_whole import recodes_whole


@dataclass(frozen=True, slots=True)
class _MediaPicture(_MediaFacts):
    """Картинка паспорта: во что она развернётся на экране и чем за это платят."""

    @property
    def delivered_mbit(self) -> float:
        """Сколько Мбит/с уедет на ТВ в среднем (:func:`delivered_mbit`)."""
        return delivered_mbit(self.video_bps)

    def weight_mbit(self, size: int) -> float:
        """Вес видеодорожки; при молчании паспорта — размер на длительность."""
        return (
            self.video_bps / 1000000.0 if self.video_bps > 0 else bitrate_mbit(size, self.duration)
        )

    @property
    def frame(self) -> int:
        """Ступень лестницы качества, к которой относится кадр.

        По одной высоте судить нельзя: 1920×800 (обрезанный скоуп) и 1150×574 дают 800 и
        574 — числа соседние, а это 1080p и SD. Ширина отвечает на это однозначно, потому
        что кадрируют по вертикали: считаем, во что кадр развернулся бы в 16:9, и берём
        большее из двух.
        """
        return max(self.height, self.width * 9 // 16)

    @property
    def interlaced(self) -> bool:
        """Кадр чересстрочный: поедет на экран гребёнкой, и об этом нельзя молчать.

        Значения ``tt``/``bb``/``tb``/``bt`` - порядок полей, который ffprobe читает
        из самого потока; ``progressive`` и молчание паспорта - обычный кадр.
        """
        return (self.field_order or "") in {"tt", "bb", "tb", "bt"}

    @property
    def quality(self) -> str:
        """Качество словами: ``1080p``; ноль высоты — честный ``?``.

        Ступени лестницы называются как принято (2160p/1080p/720p), всё, что ниже, —
        своей высотой: «574p» у «Моаны 2» и есть ответ на вопрос «что уехало на ТВ».

        Буква в конце - развёртка ПО ФАЙЛУ (:attr:`interlaced`), а не по имени раздачи:
        чересстрочный релиз, названный «1080p», называется «1080i», потому что именно
        гребёнка уедет на экран.
        """
        scan = "i" if self.interlaced else "p"
        for step in (2160, 1080, 720):
            if self.frame >= step * 0.95:
                return f"{step}{scan}"
        return f"{self.height}{scan}" if self.height else "?"

    @property
    def depth(self) -> int:
        """Глубина цвета картинки в битах (:func:`color_depth`); ``0`` - видео тут нет."""
        return color_depth(self.pix_fmt, self.profile) if self.video else 0

    @property
    def hdr(self) -> bool:
        """Картинка в HDR: яркость записана не той кривой, которой её покажет SDR-экран.

        Признак ровно один - кривая (:attr:`color_trc`), и подменять её соседями нельзя:
        десятибитный HEVC в BT.2020 бывает и обычным SDR, а 4К - тем более. HDR делает
        именно ``smpte2084`` (PQ, HDR10 и Dolby Vision) или ``arib-std-b67`` (HLG).

        Молчание паспорта (mp4 без тегов, кривой ремукс) читается как SDR: тонемап на
        SDR-исходнике портит картинку ровно так же, как его отсутствие - на HDR.
        """
        return (self.color_trc or "") in {"smpte2084", "arib-std-b67"}

    @property
    def recoded_whole(self) -> bool:
        """Этот файл придётся перекодировать целиком (:func:`recodes_whole`).

        Признак файла, а не куска: приёмник либо декодирует поток, либо нет, и середины
        тут не бывает. Ровно поэтому решение и принимается один раз по паспорту.

        ⚠️ Судит ОСТОРОЖНЫМ профилем: паспорт файла ничего не знает про приёмник, а свой
        приёмник есть не у каждого, кто спрашивает (таблица релизов, строка «перекодирую
        целиком»). Там, где от ответа зависит НАРЕЗКА, спрашивать надо
        :func:`recodes_whole` с профилем показа - иначе прогретое ляжет под другим ключом.
        """
        return recodes_whole(self.video or "", self.depth, frame=self.frame)

    @property
    def video_name(self) -> str:
        """Как называть эту картинку человеку (:func:`codec_name`)."""
        return codec_name(self.video or "", self.depth)

    @property
    def video_warning(self) -> str:
        """Пустая строка, если ресиверу это точно по зубам (HEVC и экзотика).

        ⚠️ Строка честна ровно там, где перекодирования нет: при включённом
        перекодировании HEVC мы берём на себя целиком, и говорит об этом
        :func:`recode_note`, а не она (:meth:`torrcast.cli.Bench.resolve`).

        Десятибитный H.264 сюда попадает наравне с HEVC, хотя зовётся ``h264``: на живом
        Q70D он встаёт (:data:`COPY_DEPTH`), и молчать об этом - та же подмена. Кадр 4К -
        туда же: без перекодирования его не ужать, а копией приёмник его не берёт (TC-157).

        Спрашивается тот же единственный судья, что и у показа
        (:meth:`torrcast.domain.profile.Profile.verdict`): строка и решение обязаны говорить об
        одном файле одно и то же.
        """
        if not recodes_whole(self.video or "", self.depth, frame=self.frame):
            return ""
        return f"внимание: видео {self.video_name} - ресивер может не взять, а мы не перекодируем"
