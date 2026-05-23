"""
EMA Crossover + RSI filter.

BUY  — fast EMA crosses above slow EMA AND RSI < rsi_overbought
SELL — fast EMA crosses below slow EMA AND RSI > rsi_oversold

Frequency: LOW — crossovers are rare, best on 1h/4h.
"""

import pandas as pd
import ta as ta_lib
from loguru import logger

from app.core.strategy import Signal


def generate(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_period: int = 14,
    rsi_overbought: float = 70.0,
    rsi_oversold: float = 30.0,
    **_kwargs,
) -> Signal:
    min_rows = ema_slow + rsi_period + 1
    if len(df) < min_rows:
        return Signal.NONE

    close = df["close"]
    fast = ta_lib.trend.EMAIndicator(close=close, window=ema_fast).ema_indicator()
    slow = ta_lib.trend.EMAIndicator(close=close, window=ema_slow).ema_indicator()
    rsi  = ta_lib.momentum.RSIIndicator(close=close, window=rsi_period).rsi()

    prev_fast, curr_fast = fast.iloc[-2], fast.iloc[-1]
    prev_slow, curr_slow = slow.iloc[-2], slow.iloc[-1]
    curr_rsi = rsi.iloc[-1]

    if prev_fast <= prev_slow and curr_fast > curr_slow and curr_rsi < rsi_overbought:
        logger.debug(f"[EMA_CROSS] BUY — EMA({ema_fast}/{ema_slow}) cross up, RSI={curr_rsi:.1f}")
        return Signal.BUY

    if prev_fast >= prev_slow and curr_fast < curr_slow and curr_rsi > rsi_oversold:
        logger.debug(f"[EMA_CROSS] SELL — EMA({ema_fast}/{ema_slow}) cross down, RSI={curr_rsi:.1f}")
        return Signal.SELL

    return Signal.NONE
