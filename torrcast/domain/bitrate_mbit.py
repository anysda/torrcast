"""Считает средний битрейт медиафайла."""


def bitrate_mbit(size: int, duration: float) -> float:
    """Средний битрейт раздачи, Мбит/с — предел декодера Q70D ~20."""
    return size * 8 / duration / 1000000.0 if size > 0 and duration > 0 else 0.0
