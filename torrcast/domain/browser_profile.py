"""Измеренный профиль приёмника-вкладки: тот же браузер, что открыл страницу продукта."""

from typing import Final

from torrcast.domain.receiver_profile import ReceiverProfile
from torrcast.domain.segment_container import FMP4

__all__ = ["BROWSER"]

BROWSER: Final = ReceiverProfile(
    key="browser",
    title_key="receiver.profile_browser",
    # hls.js кормит MSE напрямую CMAF-куском без перепаковки в JS; тракт, которым это
    # прощупано (:mod:`scripts.decodebench`, метод ниже), - fmp4, а не mpegts.
    # снято: decodebench · fmp4 · TC-1108
    segment_container=FMP4,  # снято: decodebench · fmp4 · TC-1108
    # ТЗ называло 20 Мбит/с потолком перекода для браузера ГИПОТЕЗОЙ (против 10 у
    # Samsung) - и был неправ вдвое с половиной. Живой замер: реальный кусок фильма
    # (Interstellar, 40.77 с, исходно 1280x720 h264 24000/1001 fps по ffprobe) уложен
    # ffmpeg восемью ступенями 1920x1080 fMP4-HLS (10/15/20/25/30/40/50/60 Мбит/с,
    # ``ffmpeg -vf scale=1920:1080 -c:v libx264 -preset veryfast -b:v <N>M -maxrate <N>M
    # -bufsize <N>M -f hls -hls_segment_type fmp4``, см. ``scripts/decodebench.py pack``)
    # и прогнан в headless Chromium на CT502 (4 vCPU, без GPU) через hls.js и
    # ``HTMLVideoElement.getVideoPlaybackQuality()`` (``scripts/decodebench.py probe``).
    # Ступени 10-50 Мбит/с доиграли все 978 кадров без единого пропуска и ровно в
    # реальном темпе (40.87 с клипа - 40.87 с прогона). На 60 Мбит/с декодер отстал: за
    # 60 с настенных часов позиция дошла только до 39.7 с из 40.87 - декодер не успевал,
    # хотя счётчик пропущенных кадров молчал (он ловит выброшенные компоновщиком кадры,
    # а не отставание темпа). Параллельный ``pidstat -u 2`` в это же время показывал до
    # ~121% одного ядра - декодер работал взаправду, а не заглушкой. Потолок взят по
    # последней ступени с доказанным реальным темпом: 50, а не 60 и не 20 Мбит/с.
    # снято: decodebench · fmp4 · TC-1108
    recode_at_mbit=50.0,  # снято: decodebench · fmp4 · TC-1108
    # Цель перекода и потолок отбора зеркалят измеренный потолок разбора - тем же
    # основанием, что и у :data:`torrcast.domain.android_tv_profile.ANDROID_TV`
    # (её recode_at_mbit/recode_mbit/warn_mbit равны друг другу по той же причине).
    # снято: decodebench · fmp4 · TC-1108
    recode_mbit=50.0,  # снято: decodebench · fmp4 · TC-1108
    warn_mbit=50.0,  # снято: decodebench · fmp4 · TC-1108
    # Обе границы молчания - слово карточки (ТЗ §7.4: 15 с - «lost», не поднимаем сами;
    # 60 с - штатное закрытие тем же путём, каким закрывают потерянный телевизор), а не
    # числа, подобранные наблюдением за настоящим декодером: у браузера нет своего
    # физического предела терпения, который стоило бы открывать замером. Прогнано живьём
    # (``scripts/staleprobe.py``) ровно на то, что код держит эти же секунды, а не другие:
    # сеанс встаёт «lost» на 15.0 с молчания и переходит в ``playing=False`` на 60.0 с -
    # без единого «почти».
    # снято: staleprobe · не при чём · TC-1108
    lost_after=15.0,  # снято: staleprobe · не при чём · TC-1108
    gone_after=60.0,  # снято: staleprobe · не при чём · TC-1108
)
