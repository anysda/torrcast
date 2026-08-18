"""Порт индикатора: договор, умолчание и слот назначенного завода."""

from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.quiet import Quiet
from torrcast.ports.progress.slot import factory, install, progress

__all__ = ["Progress", "Quiet", "factory", "install", "progress"]
