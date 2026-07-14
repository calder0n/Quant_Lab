"""Gymnasium-compatible trading environment.

Observation: the causal feature vector of the current bar (indicators, price
returns, volume, volatility, hour, spread) plus the current position.
Actions: 0 = wait, 1 = buy (long), 2 = sell (short), 3 = close.
Reward: position * log-return of the next bar, minus a transaction cost on
every position change. One episode walks the data window once.
"""

from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

ACTION_WAIT = 0
ACTION_BUY = 1
ACTION_SELL = 2
ACTION_CLOSE = 3


class TradingEnv(gym.Env[np.ndarray, int]):
    """Single-instrument discrete-position trading environment."""

    metadata = {"render_modes": []}  # noqa: RUF012 - instance attr in gym.Env

    def __init__(
        self,
        features: pd.DataFrame,
        close: pd.Series,
        cost_pct: float = 0.0002,
    ) -> None:
        super().__init__()
        if len(features) != len(close):
            raise ValueError("features and close must be aligned")
        matrix = features.to_numpy(dtype=np.float32)
        if np.isnan(matrix).any():
            raise ValueError("features contain NaN; drop warmup rows first")
        self._features = matrix
        self._log_returns = np.diff(np.log(close.to_numpy(dtype=np.float64)))
        self._cost = float(cost_pct)
        self._step_index = 0
        self._position = 0
        self.equity = 1.0
        self.trades = 0

        n_features = matrix.shape[1] + 1  # + current position
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(n_features,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(4)

    def _observation(self) -> np.ndarray:
        return np.append(self._features[self._step_index], np.float32(self._position)).astype(
            np.float32
        )

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        self._step_index = 0
        self._position = 0
        self.equity = 1.0
        self.trades = 0
        return self._observation(), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        target = {
            ACTION_WAIT: self._position,
            ACTION_BUY: 1,
            ACTION_SELL: -1,
            ACTION_CLOSE: 0,
        }[int(action)]
        cost = self._cost * abs(target - self._position)
        if target != self._position:
            self.trades += 1
        self._position = target

        log_return = float(self._log_returns[self._step_index])
        reward = self._position * log_return - cost
        self.equity *= float(np.exp(self._position * log_return)) * (1.0 - cost)

        self._step_index += 1
        terminated = self._step_index >= len(self._log_returns)
        observation = (
            self._observation()
            if not terminated
            else np.append(self._features[-1], np.float32(self._position)).astype(np.float32)
        )
        info = {"equity": self.equity, "position": self._position, "trades": self.trades}
        return observation, reward, terminated, False, info
