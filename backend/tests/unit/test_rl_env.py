"""Tests for the Gymnasium trading environment."""

import numpy as np
import pytest

from quantlab.ml.features import WARMUP_BARS, build_features, feature_names
from quantlab.rl.env import ACTION_BUY, ACTION_CLOSE, ACTION_SELL, ACTION_WAIT, TradingEnv
from tests.factories import make_market_data


def make_env(bars: int = 300, cost_pct: float = 0.001) -> TradingEnv:
    data = make_market_data(bars)
    features = build_features(data).iloc[WARMUP_BARS:][feature_names()]
    close = data["close"].iloc[WARMUP_BARS:]
    return TradingEnv(features, close, cost_pct=cost_pct)


def test_env_follows_the_gymnasium_api() -> None:
    from stable_baselines3.common.env_checker import check_env

    check_env(make_env(), warn=False)


def test_observation_includes_features_and_position() -> None:
    env = make_env()
    observation, _ = env.reset(seed=1)
    assert observation.shape == (len(feature_names()) + 1,)
    assert observation[-1] == 0.0  # flat
    observation, _, _, _, _ = env.step(ACTION_BUY)
    assert observation[-1] == 1.0  # long


def test_rewards_track_position_and_costs() -> None:
    env = make_env(cost_pct=0.01)
    env.reset(seed=1)
    _, reward_wait, _, _, _ = env.step(ACTION_WAIT)
    assert reward_wait == 0.0  # flat, no cost
    _, reward_buy, _, _, info = env.step(ACTION_BUY)
    assert reward_buy == pytest.approx(env._log_returns[1] - 0.01)
    assert info["trades"] == 1


def test_close_and_reversal_transitions() -> None:
    env = make_env()
    env.reset(seed=1)
    env.step(ACTION_BUY)
    _, _, _, _, info = env.step(ACTION_SELL)  # reversal long -> short
    assert info["position"] == -1
    _, _, _, _, info = env.step(ACTION_CLOSE)
    assert info["position"] == 0
    assert info["trades"] == 3


def test_episode_terminates_at_data_end() -> None:
    env = make_env(bars=WARMUP_BARS + 50)
    env.reset(seed=1)
    terminated = False
    steps = 0
    while not terminated:
        _, _, terminated, truncated, _ = env.step(ACTION_WAIT)
        assert not truncated
        steps += 1
    assert steps == 49  # n bars - 1 transitions


def test_long_in_rising_market_grows_equity() -> None:
    data = make_market_data(200)
    ramp = np.exp(np.linspace(0.0, 0.5, 200))
    for column in ("open", "high", "low", "close"):
        data[column] = data[column].iloc[0] * ramp
    features = build_features(data).iloc[WARMUP_BARS:][feature_names()].fillna(0.0)
    close = data["close"].iloc[WARMUP_BARS:]
    env = TradingEnv(features, close, cost_pct=0.0)
    env.reset(seed=1)
    env.step(ACTION_BUY)
    terminated = False
    while not terminated:
        _, _, terminated, _, _ = env.step(ACTION_WAIT)
    assert env.equity > 1.2


def test_nan_features_are_rejected() -> None:
    data = make_market_data(100)
    features = build_features(data)[feature_names()]  # contains warmup NaN
    with pytest.raises(ValueError, match="NaN"):
        TradingEnv(features, data["close"])
