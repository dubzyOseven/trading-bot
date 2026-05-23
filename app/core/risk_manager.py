"""
Risk management: ATR-based stop-loss/take-profit + position sizing.

Position size formula:
    risk_amount  = equity * (risk_percent / 100)
    pip_risk     = |entry - stop_loss| / pip_value
    volume       = risk_amount / (pip_risk * pip_value_per_lot)

For simplicity we use a fixed pip_value_per_lot of 10 USD (standard lot, USD-denominated pair).
For cross-pairs adjust pip_value_per_lot accordingly.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import ta as ta_lib
from loguru import logger


@dataclass
class RiskLevels:
    volume: float          # lots
    stop_loss: float
    take_profit: float


def calculate_risk_levels(
    df: pd.DataFrame,
    signal_direction: str,        # "BUY" or "SELL"
    current_price: float,
    equity: float,
    risk_percent: float = 1.0,
    atr_period: int = 14,
    atr_sl_multiplier: float = 1.5,
    atr_tp_multiplier: float = 2.5,
    pip_value_per_lot: float = 10.0,   # USD per pip per standard lot
    min_volume: float = 0.01,
    max_volume: float = 10.0,
) -> Optional[RiskLevels]:
    """
    Returns stop-loss, take-profit, and calculated lot size.
    Returns None if ATR is unavailable.
    """
    atr_series = ta_lib.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=atr_period
    ).average_true_range()
    if atr_series is None or atr_series.empty:
        logger.warning("ATR unavailable — skipping trade.")
        return None

    atr = atr_series.iloc[-1]
    if atr <= 0:
        logger.warning(f"ATR is zero or negative ({atr}) — skipping trade.")
        return None

    sl_distance = atr * atr_sl_multiplier
    tp_distance = atr * atr_tp_multiplier

    if signal_direction == "BUY":
        stop_loss = current_price - sl_distance
        take_profit = current_price + tp_distance
    else:
        stop_loss = current_price + sl_distance
        take_profit = current_price - tp_distance

    # Determine pip size and minimum volume based on asset price range
    if current_price < 10:
        pip_size = 0.0001        # standard forex (EURUSD, GBPUSD …)
        auto_min_volume = 0.01
    elif current_price < 200:
        pip_size = 0.001         # JPY pairs or low-price assets
        auto_min_volume = 0.01
    else:
        pip_size = 0.01          # crypto, gold, indices
        auto_min_volume = 0.1    # brokers require min 0.1 lot for high-priced assets

    effective_min = max(min_volume, auto_min_volume)

    risk_amount = equity * (risk_percent / 100.0)
    pip_risk = sl_distance / pip_size
    raw_volume = risk_amount / max(pip_risk * pip_value_per_lot, 0.01)
    volume = round(max(effective_min, min(float(raw_volume), max_volume)), 2)

    logger.debug(
        f"Risk calc | equity={equity:.2f} risk={risk_percent}% "
        f"ATR={atr:.5f} SL={stop_loss:.5f} TP={take_profit:.5f} vol={volume}"
    )
    return RiskLevels(
        volume=float(volume),
        stop_loss=float(round(stop_loss, 5)),
        take_profit=float(round(take_profit, 5)),
    )
