"""Мост torrcast для Home Assistant: HTTP на :8479 и анонс себя по mDNS.

Пакет - адаптер и только адаптер. Каждый маршрут зовёт существующий вход продукта:
показ - ту же :func:`torrcast.cli.main.main`, что и консоль с ботом; пульт - тот же файл
одноразовых команд (:data:`torrcast.domain.debug_handles.CTL_ENV`), в который пишут кнопки
бота; снимок - тот же :class:`torrcast.domain.playback_snapshot.PlaybackSnapshot`, которым
отвечает ``cast status``. Своих правил показа тут нет ни одного.
"""
