"""Конфиг и состояние просмотра: ``/etc/torrcast/config.json`` (обязателен только
адрес ТВ) и ``/var/lib/torrcast/state.json`` (запись атомарная: tmp + rename).
Обе точки переопределяются переменными окружения ``TORRCAST_STATE`` и
``TORRCAST_CONFIG`` — это нужно тестам и локальному запуску.
"""
