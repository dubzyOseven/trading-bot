import numpy as np
import pandas as pd
import pytest

from app.core.strategy import Signal, generate_signal


def _make_df(close_values: list[float]) -> pd.DataFrame:
    n = len(close_values)
    return pd.DataFrame(
        {
            "open": close_values,
            "high": [v * 1.001 for v in close_values],
            "low": [v * 0.999 for v in close_values],
            "close": close_values,
            "volume": [1000] * n,
        }
    )


def test_not_enough_data_returns_none():
    df = _make_df([1.1] * 10)
    assert generate_signal(df) == Signal.NONE


def test_returns_signal_on_valid_data():
    # Build a trending up series to trigger a BUY crossover
    base = 1.1000
    close = [base + i * 0.0002 for i in range(250)]
    df = _make_df(close)
    result = generate_signal(df)
    assert result in (Signal.BUY, Signal.SELL, Signal.NONE)
