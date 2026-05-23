"""
MACD Histogram Reversal.

BUY  — MACD histogram turns positive (crosses above zero) AND close > EMA(50) trend filter
SELL — MACD histogram turns negative (crosses below zero) AND close < EMA(50) trend filter

Frequency: MEDIUM-HIGH — histogram changes direction frequently on 5m/15m.
The EMA(50) trend filter avoids trading against the dominant direction.
"""

import pandas as pd
import ta as ta_lib
from loguru import logger

from app.core.strategy import Signal


def generate(
    df: pd.DataFrame,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    trend_ema: int = 50,
    **_kwargs,
) -> Signal:
    min_rows = macd_slow + macd_signal + trend_ema + 1
    if len(df) < min_rows:
        return Signal.NONE

    close = df["close"]

    macd_ind = ta_lib.trend.MACD(
        close=close,
        window_fast=macd_fast,
        window_slow=macd_slow,
        window_sign=macd_signal,
    )
    histogram = macd_ind.macd_diff()
    trend = ta_lib.trend.EMAIndicator(close=close, window=trend_ema).ema_indicator()

    prev_hist = histogram.iloc[-2]
    curr_hist = histogram.iloc[-1]
    curr_close = close.iloc[-1]
    curr_trend = trend.iloc[-1]

    # Histogram flipped positive + price is above the trend EMA (uptrend)
    if prev_hist <= 0 and curr_hist > 0 and curr_close > curr_trend:
        logger.debug(f"[MACD] BUY — histogram turned positive ({prev_hist:.5f} → {curr_hist:.5f}), price above EMA{trend_ema}")
        return Signal.BUY

    # Histogram flipped negative + price is below the trend EMA (downtrend)
    if prev_hist >= 0 and curr_hist < 0 and curr_close < curr_trend:
        logger.debug(f"[MACD] SELL — histogram turned negative ({prev_hist:.5f} → {curr_hist:.5f}), price below EMA{trend_ema}")
        return Signal.SELL

    return Signal.NONE
