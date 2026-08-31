"""Русские строки мастера Telegram."""


def ru() -> dict[str, str]:
    """Вернуть русский каталог."""
    return {
        "menu": (
            "Настройка Telegram-бота\n1. Токен бота\n2. ID чата\n3. Прокси\n"
            "4. Проверить и сохранить\n5. Снести настройку\n0. Выйти"
        ),
        "choice": "Выберите шаг: ",
        "token": "Токен бота: ",
        "chat": "ID чата: ",
        "proxy": "Прокси (http://, https://, socks5:// или socks5h://; пусто — оставить): ",
        "token_set": "Токен задан ({token}).",
        "chat_set": "ID чата задан.",
        "proxy_set": "Прокси задан.",
        "need_fields": "Сначала задайте токен бота и ID чата.",
        "testing": "Проверяю getMe и отправляю живое пробное сообщение...",
        "test_message": "Проверка настройки Telegram torrcast: бот может писать сюда.",
        "success": "Живая проверка прошла; конфиг сохранён с режимом 0600.",
        "service_up": (
            "Служба бота поднята и включена: отвечает сейчас и вернётся после перезагрузки "
            "(systemctl status torrcast-bot)."
        ),
        "service_down": (
            "Сохранено, но служба бота не поднялась: {detail}. Пока её нет, чат не читает "
            "никто; подними руками: systemctl enable --now torrcast-bot."
        ),
        "removed": "Настройка Telegram удалена.",
        "nothing_removed": "Настройки Telegram не было.",
        "invalid_choice": "Нет такого шага меню.",
        "invalid_proxy": "Это не поддерживаемый прокси; дайте socks5:// или http://.",
        "mtproto": "Это MTProto-прокси. Bot API через него не работает; дайте socks5:// или http://.",
        "network": "Сеть до api.telegram.org не открылась либо истёк таймаут: {detail}",
        "http_401": "401: токен бота неверный.",
        "http_403": "403: бот не в чате либо у него нет прав.",
        "http_400": "400: указан неверный chat_id.",
        "http_other": "Telegram API ответил HTTP {status}: {detail}",
        "try_proxy": (
            "Проверка не прошла. Вставьте прокси или нажмите Enter, чтобы остаться в настройке: "
        ),
        "choice_timeout": "Время выбора картины вышло. Отправьте команду cast ещё раз.",
        "choice_expired": "Это меню картин уже не действует.",
        "help": "cast <фильм> s1e1 [-2] · cast stop / pause / resume / status",
        "busy": "Предыдущий запрос cast ещё выполняется.",
        "failed": "Каст не начался: {detail}",
        "invalid_config_object": "битая настройка {path}: ожидался объект JSON",
        "unavailable": "Телевизор недоступен.",
        "chosen": "Картина выбрана.",
        "cancel": "Отмена",
        "cancelled": "Выбор отменён, ничего не запускаю.",
        "control_done": "Готово.",
    }
