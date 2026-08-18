"""Динамический битрейт: тяжёлые куски фильма перекодируются заранее.

Зачем. Тяжёлый кусок приёмник не доигрывает: рабочий потолок битрейта у приёмника
разработки (Samsung Q70D) - **~10 Мбит/с** (замер; прежние «15» и «18-22» опровергнуты),
и живёт это число в его профиле (:attr:`torrcast.profile.Profile.recode_at_mbit`), а не
здесь. Лечить это отбором (не брать честный тяжёлый 1080p вовсе) — значит терять
качество там, где оно есть. Тяжесть снимается не отбором, а перекодированием, и только
там, где она есть.

Как это вообще возможно без ребуферов. Три замеренных факта:

1. **Профиль тяжести известен со старта.** Карта опорных кадров
   (:mod:`torrcast.domain.frames.keymap`) несёт время и абсолютное смещение каждого
   опорного кадра, то есть байты и секунды КАЖДОГО сегмента сетки — до того, как упакован
   хоть один. Считается это из уже снятой карты, то есть даром.
2. **Байты карты — это контейнер целиком, а на ТВ уезжает только видео и одна дорожка.**
   У «Моаны 2» (13.3 ГБ) десять звуковых дорожек и восемь субтитров: контейнер идёт
   19.2 Мбит/с, а на ТВ уезжает 15.1. Поправка постоянна (замер: 4.0…4.3 Мбит/с на восьми
   сегментах подряд), поэтому она **вычитается** — и уточняется по факту первых же
   выложенных сегментов (:meth:`Weights.calibrate`).
3. **Кодировать успеваем.** libx264 на 4 vCPU E5-2696 v4, 1080p, кап 12–13 Мбит/с:
   ``veryfast`` — 1.54× реального времени, ``superfast`` — 2.62×, ``ultrafast`` — 4.36×
   (замер `scripts/recodebench.py`). Тяжёлого в «Моане 2» 46 % фильма, и модель показа
   (тот же скрипт, ключ ``--plan``) говорит: при 1.54× опаздывает ОДИН сегмент из 192 —
   ``v0``, тяжёлый с нулевой секунды, до которого фора не набирается ни при какой скорости.

⚠️ Грабля, стоившая отладки: при ``-c:v copy`` ffmpeg по ``-ss`` встаёт на опорный кадр
**раньше** запрошенного и докатывает до границы, а при перекодировании тот же
``-ss`` работает точно — лишние кадры декодируются и выбрасываются. То есть у
перекодирующего прогона докатки нет вовсе, и ``at`` равен границе сетки ровно. Первая
версия честно мерила ``at`` пробным прогоном, как для копии, и весь прогон уезжал ровно на
один сегмент: ``v359`` содержал место ``v360``.

⚠️ Вторая грабля: ``-force_key_frames`` сравнивает время кадра с запрошенным как есть, а
граница печатается с тремя знаками. Округление вверх (4909.9167 → «4909.917») уводило
опорный кадр на следующий, и на стыке копии с перекодом терялся один кадр. Поэтому
принудительные опорные кадры просятся на :data:`torrcast.domain.hls_settings.SPLIT_SLACK` раньше
границы — ровно тот же допуск, с которым режет сегментный муксер.
"""

from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.encode_settings import (
    FIT_FLOOR,
    FIT_SLACK,
    MAXRATE_GAIN,
    TONEMAP,
    VBV_SECONDS,
)
from torrcast.adapters.recode.hold_head import HEAD_LIMIT
from torrcast.adapters.recode.level_for import level_for
from torrcast.adapters.recode.pace import NEIGHBOUR_TOLL, PACE_MEMORY, Pace
from torrcast.adapters.recode.preset_for import DEADLINE_MARGIN, REALTIME, preset_for
from torrcast.adapters.recode.presets import PRESETS
from torrcast.adapters.recode.recode_dir import RECODE_DIR
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.recoder_settings import RUN_MAX
from torrcast.adapters.recode.run import HEAD_NICE, NICE
from torrcast.adapters.recode.weights import PASSPORT_WEIGHT, Weights
from torrcast.adapters.recode.whole_encode import (
    FULL_FLOOR,
    FULL_GAIN,
    FULL_PRESET,
    whole_encode,
)
from torrcast.adapters.recode.yield_to_shrink import SHRINK_FRESH
from torrcast.domain.recode_settings import RECODE_HEIGHT

__all__ = [
    "DEADLINE_MARGIN",
    "FIT_FLOOR",
    "FIT_SLACK",
    "FULL_FLOOR",
    "FULL_GAIN",
    "FULL_PRESET",
    "HEAD_LIMIT",
    "HEAD_NICE",
    "MAXRATE_GAIN",
    "NEIGHBOUR_TOLL",
    "NICE",
    "PACE_MEMORY",
    "PASSPORT_WEIGHT",
    "PRESETS",
    "REALTIME",
    "RECODE_DIR",
    "RECODE_HEIGHT",
    "RUN_MAX",
    "SHRINK_FRESH",
    "TONEMAP",
    "VBV_SECONDS",
    "Encode",
    "Pace",
    "Recoder",
    "Weights",
    "level_for",
    "preset_for",
    "whole_encode",
]
