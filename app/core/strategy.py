"""
EMA Crossover + RSI filter strategy.

Signal logic:
  BUY  — fast EMA crosses above slow EMA AND RSI < 70 (not overbought)
  SELL — fast EMA crosses below slow EMA AND RSI > 30 (not oversold)
  NONE — no signal

All parameters are configurable via BotConfig.
"""

from enum import Enum
from typing import Optional

import pandas as pd
import ta as ta_lib
from loguru import logger


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NONE = "NONE"


def generate_signal(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_period: int = 14,
    rsi_overbought: float = 70.0,
    rsi_oversold: float = 30.0,
) -> Signal:
    """
    Analyse the last two candles of a OHLCV DataFrame and return a trading signal.
    Requires at least `ema_slow + rsi_period + 1` rows.
    """
    min_rows = ema_slow + rsi_period + 1
    if len(df) < min_rows:
        logger.warning(f"Not enough candles ({len(df)}) — need at least {min_rows}.")
        return Signal.NONE

    close = df["close"]

    fast = ta_lib.trend.EMAIndicator(close=close, window=ema_fast).ema_indicator()
    slow = ta_lib.trend.EMAIndicator(close=close, window=ema_slow).ema_indicator()
    rsi = ta_lib.momentum.RSIIndicator(close=close, window=rsi_period).rsi()

    if fast is None or slow is None or rsi is None:
        return Signal.NONE

    prev_fast, curr_fast = fast.iloc[-2], fast.iloc[-1]
    prev_slow, curr_slow = slow.iloc[-2], slow.iloc[-1]
    curr_rsi = rsi.iloc[-1]

    bullish_cross = prev_fast <= prev_slow and curr_fast > curr_slow
    bearish_cross = prev_fast >= prev_slow and curr_fast < curr_slow

    if bullish_cross and curr_rsi < rsi_overbought:
        logger.debug(f"BUY signal — EMA({ema_fast}/{ema_slow}) cross up, RSI={curr_rsi:.1f}")
        return Signal.BUY

    if bearish_cross and curr_rsi > rsi_oversold:
        logger.debug(f"SELL signal — EMA({ema_fast}/{ema_slow}) cross down, RSI={curr_rsi:.1f}")
        return Signal.SELL

    return Signal.NONE
