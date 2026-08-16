"""Отвечает тестам паспортом потока по куску его адреса и помнит все запросы."""

from __future__ import annotations

from dataclasses import dataclass, field

from torrcast.stream import AudioTrack, Media

#: Паспорт, которым отвечает фейк: длительность, кодек и кадр обычной раздачи 1080p.
RUNTIME = 3600.0


@dataclass
class FakeMediaProbe:
    """ffprobe без ffprobe: язык дорожки выбирается по куску адреса потока.

    Подаётся стенду отбора параметром ``prober``. Ключ - подстрока адреса (у раздачи
    в нём виден её магнит), значение - язык единственной дорожки. Адрес, не совпавший
    ни с одним ключом, получает :attr:`default`.
    """

    languages: dict[str, str] = field(default_factory=dict)
    default: str = "rus"
    asked: list[str] = field(default_factory=list)

    def __call__(self, url: str, timeout: float = 90.0, alive: object = None) -> Media:
        self.asked.append(url)
        for fragment, language in self.languages.items():
            if fragment in url:
                return self._media(language)
        return self._media(self.default)

    @staticmethod
    def _media(language: str) -> Media:
        return Media(RUNTIME, (AudioTrack(index=0, language=language),), "h264", 1080, 1920)
