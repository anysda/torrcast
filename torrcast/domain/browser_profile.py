"""Профиль вкладки браузера: то, что Chromium реально играет через hls.js."""

from typing import Final

from torrcast.domain.receiver_profile import ReceiverProfile

__all__ = ["BROWSER"]

#: 🔴 Вкладке он достаётся только там, где передать показ некому: приёмник машины -
#: вкладка, и ТВ не назван (:class:`torrcast.adapters.chromecast.profile_detector.
#: ProfileDetector`). Кнопка «На ТВ» отдаёт телевизору тот же ``url`` (:mod:`web.to_tv`),
#: и поток, упакованный под вкладку, телевизор мог бы не доиграть.
BROWSER: Final = ReceiverProfile(
    key="browser",
    title_key="receiver.profile_browser",
    # Кодеки остаются осторожными, и это замер, а не лень. ``MediaSource.isTypeSupported``
    # у Chromium: hvc1/hev1 нет ни Main, ни Main10, mp4v нет - такой файл едет перекодом,
    # копия HEVC давала чёрный экран без единого запрошенного куска. VP9 и AV1 Chromium
    # играет, но в кусок MPEG-TS их не положить, и они остаются отказом отбора. High10
    # строкой типа принимается, а живьём не проверен - остаётся перекодом.
    # снято: tabprobe · mpegts · TC-1259
    #
    # Потолки веса и длины куска у вкладки - не декодер, а запас hls.js: он держит до
    # 60 МБ и 30 с впереди, то есть два куска по 28 МБ и 15 с. Осторожные 16 МБ и
    # 10 Мбит/с резали вкладке тяжёлые куски копии склейкой и перекодом, которые она и
    # так играет: «Оно» и «Матрица» стояли на этом по 4-6 с до первого кадра.
    # снято: tabprobe · mpegts · TC-1259
    max_segment_bytes=28_000_000,  # снято: tabprobe · mpegts · TC-1259
    max_segment_seconds=15.0,  # снято: tabprobe · mpegts · TC-1259
    recode_at_mbit=28.0,  # снято: tabprobe · mpegts · TC-1259
)
