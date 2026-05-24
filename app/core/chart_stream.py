"""
Live chart streaming: MetaAPI candle subscriptions bridged to browser WebSockets.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket
from loguru import logger
from metaapi_cloud_sdk import MetaApi
from metaapi_cloud_sdk.clients.metaapi.synchronization_listener import SynchronizationListener

from app.broker.metaapi import MetaApiConnector
from app.core.config import settings

VALID_TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d"})
CANDLE_INTERVAL_MS = 5000
SNAPSHOT_COUNT = 200
STREAM_IDLE_SEC = 60


def _candle_time_unix(candle: dict) -> int:
    t = candle.get("time")
    if isinstance(t, datetime):
        if t.tzinfo is None:
            return int(t.replace(tzinfo=timezone.utc).timestamp())
        return int(t.timestamp())
    return int(t)


def meta_candle_to_out(candle: dict) -> dict[str, Any]:
    return {
        "time": _candle_time_unix(candle),
        "open": float(candle["open"]),
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "close": float(candle["close"]),
        "volume": float(candle.get("tickVolume") or candle.get("volume") or 0),
    }


def dataframe_to_candles(df) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for ts, row in df.iterrows():
        candles.append(
            {
                "time": int(ts.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return candles


async def fetch_candle_snapshot(account_id: str, symbol: str, timeframe: str) -> list[dict[str, Any]]:
    connector = MetaApiConnector(account_id)
    await connector.connect()
    try:
        df = await connector.get_candles(symbol, timeframe, SNAPSHOT_COUNT)
    finally:
        await connector.disconnect()
    return dataframe_to_candles(df)


class ChartCandleListener(SynchronizationListener):
    def __init__(self, session: ChartStreamSession) -> None:
        self._session = session

    async def on_candles_updated(
        self,
        instance_index: str,
        candles: list,
        equity: float = None,
        margin: float = None,
        free_margin: float = None,
        margin_level: float = None,
        account_currency_exchange_rate: float = None,
    ) -> None:
        for raw in candles:
            sym = (raw.get("symbol") or "").upper()
            tf = raw.get("timeframe") or ""
            if sym == self._session.symbol and tf == self._session.timeframe:
                await self._session.broadcast(
                    {"type": "update", "candle": meta_candle_to_out(raw)}
                )


class ChartStreamSession:
    def __init__(
        self,
        user_id: int,
        account_id: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        self.user_id = user_id
        self.account_id = account_id
        self.symbol = symbol.upper()
        self.timeframe = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
        self.subscribers: set[WebSocket] = set()
        self._ref_count = 0
        self._lock = asyncio.Lock()
        self._streaming = None
        self._listener: Optional[ChartCandleListener] = None
        self._account = None
        self._started = False
        self._stop_task: Optional[asyncio.Task] = None
        self._last_candles: list[dict[str, Any]] = []

    def _cancel_delayed_stop(self) -> None:
        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
        self._stop_task = None

    async def _delayed_stop(self) -> None:
        try:
            await asyncio.sleep(STREAM_IDLE_SEC)
            async with self._lock:
                if self._ref_count > 0:
                    return
            await self._stop_stream()
        except asyncio.CancelledError:
            pass

    def _schedule_delayed_stop(self) -> None:
        self._cancel_delayed_stop()
        self._stop_task = asyncio.create_task(self._delayed_stop())

    async def add_subscriber(self, ws: WebSocket) -> None:
        self._cancel_delayed_stop()
        async with self._lock:
            self.subscribers.add(ws)
            self._ref_count += 1
            first = not self._started
            if first:
                self._started = True
        if first:
            try:
                await self._start_stream()
            except Exception as exc:
                logger.exception(f"Chart stream start failed: {exc}")
                await self._stop_stream()
                await self.broadcast({"type": "error", "message": str(exc)})
                await self._release_subscriber(ws)
                raise
        else:
            await self._send_snapshot(ws)

    async def remove_subscriber(self, ws: WebSocket) -> None:
        stop = False
        async with self._lock:
            self.subscribers.discard(ws)
            self._ref_count = max(0, self._ref_count - 1)
            if self._ref_count == 0:
                stop = True
        if stop:
            self._schedule_delayed_stop()

    async def _release_subscriber(self, ws: WebSocket) -> None:
        async with self._lock:
            self.subscribers.discard(ws)
            self._ref_count = max(0, self._ref_count - 1)
            if self._ref_count == 0:
                self._started = False

    async def _start_stream(self) -> None:
        logger.info(
            f"[user={self.user_id}] Starting chart stream | {self.symbol} @ {self.timeframe}"
        )
        api = MetaApi(settings.META_API_TOKEN)
        self._account = await api.metatrader_account_api.get_account(self.account_id)

        if self._account.state not in ("DEPLOYING", "DEPLOYED"):
            await self._account.deploy()
            await self._account.wait_deployed(60)

        self._streaming = self._account.get_streaming_connection()
        await self._streaming.connect()
        await self._streaming.wait_synchronized()

        self._listener = ChartCandleListener(self)
        self._streaming.add_synchronization_listener(self._listener)

        await self._streaming.subscribe_to_market_data(
            self.symbol,
            [
                {
                    "type": "candles",
                    "timeframe": self.timeframe,
                    "intervalInMilliseconds": CANDLE_INTERVAL_MS,
                }
            ],
        )

        snapshot = await fetch_candle_snapshot(
            self.account_id, self.symbol, self.timeframe
        )
        self._last_candles = snapshot
        await self.broadcast({"type": "snapshot", "candles": snapshot})
        logger.success(
            f"[user={self.user_id}] Chart stream live | {self.symbol} @ {self.timeframe}"
        )

    async def _stop_stream(self) -> None:
        self._cancel_delayed_stop()
        logger.info(
            f"[user={self.user_id}] Stopping chart stream | {self.symbol} @ {self.timeframe}"
        )
        self._started = False
        self._last_candles = []
        if self._streaming:
            try:
                if self._listener:
                    self._streaming.remove_synchronization_listener(self._listener)
                await self._streaming.unsubscribe_from_market_data(
                    self.symbol,
                    [{"type": "candles", "timeframe": self.timeframe}],
                )
            except Exception as exc:
                logger.warning(f"Chart stream unsubscribe failed: {exc}")
            try:
                await self._streaming.close()
            except Exception as exc:
                logger.warning(f"Chart stream close failed: {exc}")
        self._streaming = None
        self._listener = None
        self._account = None

    async def _send_snapshot(self, ws: WebSocket) -> None:
        try:
            if self._last_candles:
                candles = self._last_candles
            else:
                candles = await fetch_candle_snapshot(
                    self.account_id, self.symbol, self.timeframe
                )
                self._last_candles = candles
            await ws.send_text(json.dumps({"type": "snapshot", "candles": candles}))
        except Exception as exc:
            logger.warning(f"Snapshot for late subscriber failed: {exc}")
            await ws.send_text(json.dumps({"type": "error", "message": str(exc)}))

    async def broadcast(self, message: dict) -> None:
        if message.get("type") == "snapshot" and message.get("candles"):
            self._last_candles = message["candles"]
        elif message.get("type") == "update" and self._last_candles:
            candle = message.get("candle")
            if candle:
                t = candle["time"]
                for i, c in enumerate(self._last_candles):
                    if c["time"] == t:
                        self._last_candles[i] = candle
                        break
                else:
                    self._last_candles.append(candle)
                    self._last_candles.sort(key=lambda x: x["time"])
        text = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(self.subscribers):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.remove_subscriber(ws)


class ChartStreamManager:
    def __init__(self) -> None:
        self._sessions: dict[tuple[int, str, str, str], ChartStreamSession] = {}
        self._lock = asyncio.Lock()

    def _key(self, user_id: int, account_id: str, symbol: str, timeframe: str) -> tuple:
        tf = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
        return (user_id, account_id, symbol.upper(), tf)

    async def subscribe(
        self,
        user_id: int,
        account_id: str,
        symbol: str,
        timeframe: str,
        ws: WebSocket,
    ) -> ChartStreamSession:
        key = self._key(user_id, account_id, symbol, timeframe)
        async with self._lock:
            if key not in self._sessions:
                self._sessions[key] = ChartStreamSession(
                    user_id, account_id, symbol.upper(), key[3]
                )
            session = self._sessions[key]
        await session.add_subscriber(ws)
        return session

    async def unsubscribe(
        self,
        user_id: int,
        account_id: str,
        symbol: str,
        timeframe: str,
        ws: WebSocket,
    ) -> None:
        key = self._key(user_id, account_id, symbol, timeframe)
        async with self._lock:
            session = self._sessions.get(key)
        if session:
            await session.remove_subscriber(ws)
        async with self._lock:
            session = self._sessions.get(key)
            if session and session._ref_count == 0:
                del self._sessions[key]

    async def shutdown(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.subscribers.clear()
            session._ref_count = 0
            session._cancel_delayed_stop()
            await session._stop_stream()
        logger.info("All chart streams shut down.")


chart_streams = ChartStreamManager()
