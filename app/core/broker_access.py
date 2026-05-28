"""
Serialized MetaAPI RPC access — reuses bot broker when running.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from app.broker.metaapi import MetaApiConnector
from app.core.account_stream_hub import (
    SNAPSHOT_COUNT,
    _rpc_lock,
    dataframe_to_candles,
    get_engine_for_account,
)


async def get_candles_df(
    account_id: str,
    symbol: str,
    timeframe: str,
    count: int = SNAPSHOT_COUNT,
) -> pd.DataFrame:
    sym = symbol.upper()
    engine = get_engine_for_account(account_id)
    if engine:
        return await engine._broker.get_candles(sym, timeframe, count)

    async with _rpc_lock(account_id):
        connector = MetaApiConnector(account_id)
        await connector.connect()
        try:
            return await connector.get_candles(sym, timeframe, count)
        finally:
            await connector.disconnect()


async def get_symbols_list(account_id: str) -> list[str]:
    engine = get_engine_for_account(account_id)
    if engine:
        return await engine._broker.get_symbols()

    async with _rpc_lock(account_id):
        connector = MetaApiConnector(account_id)
        await connector.connect()
        try:
            return await connector.get_symbols()
        finally:
            await connector.disconnect()


async def get_account_and_positions(
    account_id: str,
) -> Optional[tuple[dict, list]]:
    from app.core.account_stream_hub import account_hubs

    snap = account_hubs.get_terminal_snapshot(account_id)
    if snap:
        return snap

    engine = get_engine_for_account(account_id)
    if engine:
        info = await engine._broker.get_account_info()
        positions = await engine._broker.get_positions()
        account = {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.free_margin,
            "currency": info.currency,
        }
        pos_list = [
            {
                "id": p.id,
                "symbol": p.symbol,
                "direction": p.order_type.value,
                "volume": p.volume,
                "open_price": p.open_price,
                "current_price": p.current_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "profit": p.profit,
            }
            for p in positions
        ]
        return account, pos_list
    return None
