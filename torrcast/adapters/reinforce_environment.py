"""Среда справки, каталога и телеметрии для уточнения выдачи."""

from importlib import import_module


class SystemReinforceEnvironment:
    """Собирает действующие адаптеры сценария уточнения."""

    @property
    def fact_type(self) -> object:
        return import_module("torrcast.facts").Fact

    @property
    def prowlarr_type(self) -> object:
        return import_module("torrcast.search").Prowlarr

    def __getattr__(self, name: str) -> object:
        if name in {"origin", "minutes_of", "same_name"}:
            return getattr(import_module("torrcast.facts"), name)
        if name in {"merge", "to_releases"}:
            return getattr(import_module("torrcast.search"), name)
        if name == "trace":
            return import_module("torrcast.trace")
        raise AttributeError(name)


environment = SystemReinforceEnvironment()
