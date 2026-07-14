"""PPO training over the TradingEnv, with held-out policy evaluation."""

from pathlib import Path
from typing import Any

import pandas as pd


def train_ppo(
    train_features: pd.DataFrame,
    train_close: pd.Series,
    eval_features: pd.DataFrame,
    eval_close: pd.Series,
    params: dict[str, Any],
    artifact_path: Path,
) -> dict[str, Any]:
    """Train a PPO policy and evaluate it deterministically on unseen data."""
    from stable_baselines3 import PPO

    from quantlab.rl.env import TradingEnv

    cost_pct = float(params.get("cost_pct", 0.0002))
    timesteps = int(params.get("timesteps", 20_000))
    seed = int(params.get("seed", 42))

    train_env = TradingEnv(train_features, train_close, cost_pct=cost_pct)
    model = PPO(
        "MlpPolicy",
        train_env,
        seed=seed,
        verbose=0,
        n_steps=int(params.get("n_steps", 512)),
        learning_rate=float(params.get("learning_rate", 3e-4)),
    )
    model.learn(total_timesteps=timesteps, progress_bar=False)
    model.save(artifact_path)

    eval_env = TradingEnv(eval_features, eval_close, cost_pct=cost_pct)
    observation, _ = eval_env.reset(seed=seed)
    terminated = False
    while not terminated:
        action, _ = model.predict(observation, deterministic=True)
        observation, _, terminated, _, _ = eval_env.step(int(action))
    return {
        "train_timesteps": timesteps,
        "train_bars": len(train_features),
        "eval_bars": len(eval_features),
        "eval_total_return": float(eval_env.equity - 1.0),
        "eval_trades": int(eval_env.trades),
        "cost_pct": cost_pct,
    }
