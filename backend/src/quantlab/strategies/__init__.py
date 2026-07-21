"""Strategy plugin system.

Every strategy is a self-contained module under ``quantlab.strategies.plugins``
implementing the :class:`quantlab.strategies.base.Strategy` contract. Plugins
are discovered automatically by :class:`quantlab.strategies.registry.StrategyRegistry`.
"""
