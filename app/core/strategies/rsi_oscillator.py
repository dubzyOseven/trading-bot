"""
RSI Oscillator (mean-reversion).

BUY  — RSI crosses UP through the oversold threshold (was <= oversold, now > oversold)
SELL — RSI crosses DOWN through the overbought threshold (was >= overbought, now < overbought)

Frequency: HIGH — fires several times per day on 1m/5m.
Best used with tight risk settings (low risk_percent, tight ATR multipliers).
"""

import pandas as pd
import ta as ta_lib
from loguru import logger

from app.core.strategy import Signal


def generate(
    df: pd.DataFrame,
    rsi_period: int = 14,
    rsi_overbought: float = 55.0,
    rsi_oversold: float = 45.0,
    **_kwargs,
) -> Signal:
    min_rows = rsi_period + 2
    if len(df) < min_rows:
        return Signal.NONE

    close = df["close"]
    rsi = ta_lib.momentum.RSIIndicator(close=close, window=rsi_period).rsi()

    prev_rsi = rsi.iloc[-2]
    curr_rsi = rsi.iloc[-1]

    # Crossed up through oversold — price bouncing from bottom
    if prev_rsi <= rsi_oversold and curr_rsi > rsi_oversold:
        logger.debug(f"[RSI_OSC] BUY — RSI crossed up through {rsi_oversold} ({prev_rsi:.1f} → {curr_rsi:.1f})")
        return Signal.BUY

    # Crossed down through overbought — price turning from top
    if prev_rsi >= rsi_overbought and curr_rsi < rsi_overbought:
        logger.debug(f"[RSI_OSC] SELL — RSI crossed down through {rsi_overbought} ({prev_rsi:.1f} → {curr_rsi:.1f})")
        return Signal.SELL

    return Signal.NONE
