"""Порт следа: договор ленты, умолчание и слот назначенного писателя."""

from torrcast.ports.journal.journal import Journal
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install, journal

__all__ = ["Journal", "Silent", "install", "journal"]
