"""Приёмник-браузер: та же вкладка, что и у зрителя, вместо приставки на полке.

Показ и вкладка - разные процессы на одной машине, и разговаривают они только файлом
рядом с сегментами (:mod:`torrcast.usecases.playback.hls_root`), тем же способом, каким
:mod:`torrcast.adapters.stream_pack` уже сводит показ и его же CLI.

Имена берутся у своих модулей: `from torrcast.adapters.browser.browser_receiver import
BrowserReceiver`. Реэкспорта тут нет намеренно - тем же порядком, что у
:mod:`torrcast.adapters.stream_pack`.
"""

__all__: list[str] = []
