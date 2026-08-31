"""Английские строки мастера Telegram."""


def en() -> dict[str, str]:
    """Вернуть английский каталог."""
    return {
        "menu": (
            "Telegram bot setup\n1. Bot token\n2. Chat ID\n3. Proxy\n"
            "4. Test and save\n5. Remove setup\n0. Exit"
        ),
        "choice": "Choose a step: ",
        "token": "Bot token: ",
        "chat": "Chat ID: ",
        "proxy": "Proxy (http://, https://, socks5:// or socks5h://; empty keeps current): ",
        "token_set": "Token set ({token}).",
        "chat_set": "Chat ID set.",
        "proxy_set": "Proxy set.",
        "need_fields": "Set both the bot token and chat ID first.",
        "testing": "Checking getMe and sending a live test message...",
        "test_message": "torrcast Telegram setup test: the bot can post here.",
        "success": "Live check passed; configuration saved with mode 0600.",
        "service_up": (
            "The bot service is up and enabled: it answers now and returns after a reboot "
            "(systemctl status torrcast-bot)."
        ),
        "service_down": (
            "Saved, but the bot service did not come up: {detail}. Until it does, nobody "
            "reads the chat; start it by hand: systemctl enable --now torrcast-bot."
        ),
        "removed": "Telegram setup removed.",
        "nothing_removed": "There was no Telegram setup to remove.",
        "invalid_choice": "Unknown menu step.",
        "invalid_proxy": "That is not a supported proxy URL; use socks5:// or http://.",
        "mtproto": "This is an MTProto proxy. Bot API cannot use it; provide socks5:// or http://.",
        "network": "Network access to api.telegram.org failed or timed out: {detail}",
        "http_401": "401: the bot token is invalid.",
        "http_403": "403: the bot is not in the chat or lacks permission.",
        "http_400": "400: the chat_id is invalid.",
        "http_other": "Telegram API returned HTTP {status}: {detail}",
        "try_proxy": "The check failed. Paste a proxy now, or press Enter to stay in setup: ",
        "choice_timeout": "The picture choice expired. Send the cast command again.",
        "choice_expired": "This picture menu is no longer active.",
        "help": "cast <title> s1e1 [-2] · cast stop / pause / resume / status",
        "busy": "Another cast request is still being handled.",
        "failed": "The cast did not start: {detail}",
        "invalid_config_object": "invalid configuration {path}: expected a JSON object",
        "unavailable": "The TV is unavailable.",
        "chosen": "Picture selected.",
        "cancel": "Cancel",
        "cancelled": "Choice cancelled, nothing is started.",
        "control_done": "Done.",
    }
