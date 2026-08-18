"""Порт состояния просмотра: договор, умолчание и слот назначенного хранилища."""

from torrcast.ports.state_store.ephemeral import Ephemeral
from torrcast.ports.state_store.slot import install, store
from torrcast.ports.state_store.state_store import StateStore

__all__ = ["Ephemeral", "StateStore", "install", "store"]
