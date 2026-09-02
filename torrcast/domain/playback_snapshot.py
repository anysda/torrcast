"""Описывает сохранённый показ для команд stop и status."""

from dataclasses import dataclass

from torrcast.domain.spoken_title import spoken_title


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    """Данные показа, уже прочитанные внешним хранилищем."""

    key: str
    title: str
    position: float = 0.0
    duration: float = 0.0
    label: str = ""
    quality: str = ""
    dark_since: float = 0.0
    dark_reason: str = ""
    warm: float = 0.0
    file_index: int = 0
    audio_index: int = 0
    #: Хэш раздачи из магнита записи: им ``cast stop`` сносит пережившую юнит раздачу.
    torrent_hash: str = ""
    done: bool = False
    year: int = 0
    #: Оригинальное имя картины из записи: под EN печатается оно, а не :attr:`title`.
    original: str = ""

    @property
    def spoken(self) -> str:
        """Имя картины для человека: под EN - оригинальное, если оно записано."""
        return spoken_title(self.title, self.original)

    @property
    def shown_as(self) -> str:
        return f"«{self.spoken}»" + (f" {self.label}" if self.label else "")

    @property
    def resumable(self) -> bool:
        return self.position > 0 and not self.done
