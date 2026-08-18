"""Профиль тяжести фильма: сколько Мбит/с уедет на ТВ в каждом сегменте сетки.

Считает его по карте опорных кадров кодировщик; спрашивают его же щупы замера."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from torrcast.adapters.stream_pack.grid import Grid
    from torrcast.domain.film_keys import FilmKeys


#: Вес паспорта ffprobe в скользящем среднем :meth:`Weights.calibrate`. Паспорт - это
#: среднее по ВСЕМУ фильму, а один выложенный сегмент - шумный замер: пусть факт правит
#: паспорт, но не с первого же куска.
PASSPORT_WEIGHT: Final = 6


@dataclass(slots=True)
class Weights:
    """Профиль тяжести фильма: сколько Мбит/с уедет на ТВ в каждом сегменте сетки.

    Считается из карты опорных кадров до всякой упаковки. Байты карты — контейнер целиком,
    поэтому из них вычитается всё, что на ТВ не уезжает (:attr:`extra`), а само это число
    уточняется по факту (:meth:`calibrate`).
    """

    #: Мбит/с по контейнеру для каждого слота сетки.
    raw: tuple[float, ...]
    #: Что в контейнере есть, а на ТВ не уезжает: лишние дорожки и субтитры, Мбит/с.
    extra: float = 0.0
    #: Сколько замеров легло в :attr:`extra` (0 - только оценка по ffprobe).
    measured: int = 0
    #: Средний битрейт контейнера по карте, Мбит/с - тот же, что у файла целиком.
    container: float = 0.0

    @classmethod
    def of(
        cls, keys: FilmKeys, grid: Grid, extra: float = 0.0, delivered: float = 0.0
    ) -> Weights | None:
        """Профиль по карте и сетке. Карта без смещений (кэш прошлой версии) — ``None``.

        ``delivered`` — сколько Мбит/с уедет на ТВ в среднем по фильму, по паспорту
        ffprobe (:attr:`torrcast.domain.media.Media.delivered_mbit`). Дан — поправка «контейнер
        → ТВ» известна сразу и точно: это разница между средним по карте и им. Не дан
        (mp4 без тегов, паспорт молчит) — поправка набирается вслепую по первым
        выложенным копиям (:meth:`calibrate`).
        """
        if not keys.offset or len(keys.offset) != len(keys.at) or len(keys.at) < 3:
            return None
        raw: list[float] = []
        for slot in range(grid.count):
            span = grid.span(slot)
            head = keys.byte_at(grid.start(slot))
            tail = keys.byte_at(grid.end(slot))
            # У последнего сегмента следующей границы нет, и хвост файла картой не описан:
            # берём вес предыдущего. Один сегмент из полутысячи - цена честнее выдумки.
            if slot + 1 >= grid.count or tail <= head:
                raw.append(raw[-1] if raw else 0.0)
                continue
            raw.append((tail - head) * 8 / span / 1e6 if span > 0 else 0.0)
        total = sum(grid.span(s) for s in range(grid.count))
        container = sum(w * grid.span(s) for s, w in enumerate(raw)) / total if total > 0 else 0.0
        found = cls(raw=tuple(raw), extra=extra, container=container)
        if delivered > 0 and container > 0:
            found.extra = max(0.0, container - delivered)
            found.measured = PASSPORT_WEIGHT
        return found

    def at(self, slot: int) -> float:
        """Сколько Мбит/с уедет на ТВ в сегменте ``slot``."""
        if not 0 <= slot < len(self.raw):
            return 0.0
        return max(0.0, self.raw[slot] - self.extra)

    def heavy(self, threshold: float) -> tuple[int, ...]:
        """Слоты, которые приёмник не потянет: ``threshold`` Мбит/с и выше."""
        return tuple(s for s in range(len(self.raw)) if self.at(s) >= threshold)

    def size(self, slot: int, span: float) -> float:
        """Сколько байт весит **копия** этого куска — предсказание по карте, без потолка.

        ⚠️ Это не то же число, которым сетка проверяет потолок веса
        (:func:`torrcast.adapters.stream_pack._weigher._weigher`): там вес зажат ``ceiling_mbit`` в
        предположении, что тяжёлый кусок перекодируют. Здесь — честный вес того, что лежит в файле,
        и именно он решает, можно ли отпустить копию наружу (:meth:`Recoder.oversize`).

        Точность замерена на «Тачках 3»: предсказание 57.8 МБ против 51.4 МБ уехавших
        на самом деле (+12 %, в безопасную сторону). То есть картой предсказывать вес
        копии МОЖНО.
        """
        return max(0.0, self.at(slot)) * max(span, 0.0) * 1e6 / 8

    def bulky(self, grid: Grid, cap: float) -> tuple[int, ...]:
        """Слоты, копия которых тяжелее ``cap`` байт, — их обязан взять кодировщик.

        Отдельно от :meth:`heavy` и не совпадает с ним: замер по картам трёх релизов
        при пороге 10 Мбит/с — «Тачки 3» 5 таких кусков вне тяжёлых, «Моана 2» 3,
        «Моана» 2016 (лёгкое кино, тяжёлых почти нет) 2 куска по 17–18.3 МБ. Каждый из
        них — это ровно тот стоп 4–8 с от слишком увесистого сегмента, только пришедший
        не битрейтом, а длиной куска на лёгком месте.
        """
        return tuple(s for s in range(len(self.raw)) if self.size(s, grid.span(s)) > cap)

    def calibrate(self, slot: int, size: int, span: float) -> None:
        """Уточнить :attr:`extra` по реально выложенному сегменту-копии.

        Скользящее среднее: одиночный сегмент может соврать (дорожки в mkv лежат
        неравномерно), а десяток — уже нет. Замер на восьми сегментах подряд дал
        разброс 3.97…4.26 Мбит/с при среднем 4.10.
        """
        if not 0 <= slot < len(self.raw) or span <= 0:
            return
        seen = size * 8 / span / 1e6
        gap = self.raw[slot] - seen
        # Здравый смысл: лишние дорожки не могут весить больше самого фильма. Всё, что
        # выходит за половину контейнера, - это не поправка, а перекодированный кусок или
        # обрезанный файл, и учиться на нём нельзя.
        if not 0.0 <= gap < self.raw[slot] * 0.5:
            return
        self.measured += 1
        weight = min(self.measured, 10)
        self.extra += (gap - self.extra) / weight
