"""Ставит флажок «картинка на экране»; зовёт показ, увидевший PLAYING."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.stream_pack.playing_flag import playing_flag
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.why import why


def mark_playing(out: Path) -> None:
    """Показ увидел ``PLAYING``: с этой секунды на экране есть изображение.

    🔴 Неудача тут не роняет показ, но и не молчит (TC-884). Флажок - единственное, чем
    показ доказывает картинку своему же ``cast``: не лёг он - CLI досидит бюджет старта и
    пойдёт гасить юнит. Пока промах глотался молча, разбираться в этом было не по чему:
    в журнале показа не оставалось ни строки о том, что доказательство не поставлено.
    Говорится это в журнал юнита - туда же, куда показ говорит всё остальное.
    """
    flag = playing_flag(out)
    try:
        flag.touch()
    except OSError as trouble:
        print(phrase("stream_pack.flag_write_failed", flag=flag, reason=why(trouble)), flush=True)
