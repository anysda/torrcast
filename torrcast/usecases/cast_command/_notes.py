"""Строки перед стартом: чем это играется, что подменено и о чём человек обязан знать.

Печатает их команда показа (:func:`_cmd_play`) - последним, что зритель уносит с собой.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.config import Config
from torrcast.domain.media import Media
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.choice.namesake_note import namesake_note
from torrcast.usecases.choice.swap_note import _is_default, swap_note
from torrcast.usecases.choice.year_note import year_note
from torrcast.usecases.playback.pack_note import pack_note
from torrcast.usecases.rank._gb import _gb
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.rank.sound_note import sound_note
from torrcast.usecases.rank.voice_note import voice_note
from torrcast.usecases.select._prep import _Prep

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.choice._passport import _Passport
    from torrcast.usecases.select.plan import Plan


def _notes(
    config: Config,
    plans: list[Plan],
    plan: Plan,
    prep: _Prep,
    media: Media,
    audio: int,
    release: Release,
    video: TorrFile,
    passport: _Passport,
    args: Args,
) -> None:
    """Всё, что показ обязан сказать до старта: вес, звук, выбор файла сборника, подмена
    картины и тёзки."""
    peak = bitrate_mbit(video.size, media.duration or plan.runtime)
    if peak > config.bitrate_warn_mbit:
        print(
            f"внимание: ~{peak:.0f} Мбит/с - тяжёлые куски перекодирую на ходу"
            if config.recode
            else f"внимание: ~{peak:.0f} Мбит/с - ресивер на таком битрейте может встать"
        )
    # Молчаливого японского не бывает: перевода в файле нет - человек слышит об этом
    # строкой, а не на слух через минуту показа.
    playable = [plan.ranked[number - 1] for number in plan.candidates(args)]
    if note := sound_note(media, audio, playable, release, prep.files, native=plan.picture.native):
        print(note)
    # Русских дорожек было несколько - говорим, сколько и что взяли: подпись дорожки
    # отвечает «что играет», а эта строка - «почему это, а не соседняя».
    if note := voice_note(media, audio, plan.picture.native):
        print(note)
    if args.pinned:  # отладочный путь: тут внутренности показывать и надо
        print(f"файл: {video.base} · {_gb(video.size)} · {_hms(media.duration)} · {media.video}")
    # Авто-выбор крупнейшего файла из нескольких - такое же авто-решение, как смена
    # картины, и молчать о нём нельзя: в раздаче-сборнике зритель иначе не узнает, что
    # играет одна часть из многих. Сериалу и ручке ``--file N`` говорить нечего: там файл
    # называет серия или сам человек.
    if plan.series is None and args.file is None and (note := pack_note(prep.files)):
        print(note)
    # 🔴 TC-198. Последняя строка перед стартом: взяли не то, что назвали вслух. Место
    # выбрано не для порядка - фазы поиска к этой секунде уехали вверх экрана, а решение
    # про КАРТИНУ человек должен унести с собой. Человек выбрал пункт меню сам - подмены
    # нет и строки нет (:func:`default_note`).
    if note := swap_note(plans, plan, args.title_query):
        print(note)
    # 🔴 TC-199/TC-200. Год дефолтной картины против независимого слова справки: имя
    # раздачи врёт («Оно» 2014, «Медведь» 2026), а год у дефолта не сверялся нигде.
    if _is_default(plans, plan) and (note := year_note(plan, passport.get(), args.title_query)):
        print(note)
    # 🔴 TC-371. Двусмысленность самих источников: под одним именем и годом картин две,
    # и развести их отбору нечем - значит человек читает об этом строкой.
    if note := namesake_note(plan, passport.get()):
        print(note)
