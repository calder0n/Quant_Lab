"""Automatic strategy plugin discovery.

Scans ``quantlab.strategies.plugins`` (or any package passed in), imports every
module and registers each concrete :class:`Strategy` subclass by its
``strategy_id``. Dropping a new file into the plugins package is all it takes
to add a strategy.
"""

import importlib
import inspect
import pkgutil

from quantlab.strategies.base import ParamValue, Strategy, StrategyMetadata


class UnknownStrategyError(KeyError):
    """Raised when a strategy id is not present in the registry."""


class StrategyRegistry:
    """Holds every discovered strategy class, keyed by ``strategy_id``."""

    def __init__(self) -> None:
        self._classes: dict[str, type[Strategy]] = {}

    def register(self, strategy_class: type[Strategy]) -> None:
        self._classes[strategy_class.strategy_id] = strategy_class

    def discover(self, package: str = "quantlab.strategies.plugins") -> "StrategyRegistry":
        """Import every module in ``package`` and register its strategies."""
        module = importlib.import_module(package)
        for info in pkgutil.iter_modules(module.__path__):
            plugin = importlib.import_module(f"{package}.{info.name}")
            for _, obj in inspect.getmembers(plugin, inspect.isclass):
                if issubclass(obj, Strategy) and not inspect.isabstract(obj):
                    self.register(obj)
        return self

    def ids(self) -> list[str]:
        return sorted(self._classes)

    def list_metadata(self) -> list[StrategyMetadata]:
        return [self._classes[strategy_id].metadata() for strategy_id in self.ids()]

    def get(self, strategy_id: str) -> type[Strategy]:
        try:
            return self._classes[strategy_id]
        except KeyError as exc:
            raise UnknownStrategyError(strategy_id) from exc

    def create(self, strategy_id: str, params: dict[str, ParamValue] | None = None) -> Strategy:
        """Instantiate and ``load()`` a strategy with the given parameters."""
        strategy = self.get(strategy_id)(**(params or {}))
        strategy.load()
        return strategy
