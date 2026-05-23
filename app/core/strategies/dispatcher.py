import pandas as pd
from loguru import logger

from app.core.strategies import ema_crossover, macd, rsi_oscillator
from app.core.strategy import Signal

_STRATEGIES = {
    "ema_crossover": ema_crossover.generate,
    "rsi_oscillator": rsi_oscillator.generate,
    "macd": macd.generate,
}

STRATEGY_NAMES = list(_STRATEGIES.keys())


def run_strategy(name: str, df: pd.DataFrame, **kwargs) -> Signal:
    fn = _STRATEGIES.get(name)
    if fn is None:
        logger.warning(f"Unknown strategy '{name}' — falling back to ema_crossover.")
        fn = ema_crossover.generate
    return fn(df, **kwargs)
