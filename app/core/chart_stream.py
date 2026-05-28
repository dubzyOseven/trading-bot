"""
Live chart streaming — delegates to shared account stream hub.
"""

from __future__ import annotations

from fastapi import WebSocket
from loguru import logger

from app.core.account_stream_hub import (
    VALID_TIMEFRAMES,
    account_hubs,
    dataframe_to_candles,
    fetch_candle_snapshot,
    friendly_metaapi_error,
    meta_candle_to_out,
)

__all__ = [
    "VALID_TIMEFRAMES",
    "chart_streams",
    "dataframe_to_candles",
    "fetch_candle_snapshot",
    "friendly_metaapi_error",
    "meta_candle_to_out",
]


class ChartStreamManager:
    async def subscribe(
        self,
        user_id: int,
        account_id: str,
        symbol: str,
        timeframe: str,
        ws: WebSocket,
    ) -> None:
        try:
            await account_hubs.subscribe_chart(
                user_id, account_id, symbol, timeframe, ws
            )
        except Exception as exc:
            logger.exception(f"Chart stream subscribe failed: {exc}")
            raise RuntimeError(friendly_metaapi_error(exc)) from exc

    async def unsubscribe(
        self,
        user_id: int,
        account_id: str,
        symbol: str,
        timeframe: str,
        ws: WebSocket,
    ) -> None:
        await account_hubs.unsubscribe_chart(
            user_id, account_id, symbol, timeframe, ws
        )

    async def shutdown(self) -> None:
        pass  # hub shutdown handled once in main lifespan


chart_streams = ChartStreamManager()
