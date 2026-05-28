"""
One MetaAPI streaming connection per MT5 account.

Dashboard account/position updates and chart candle feeds share the same
streaming connection and synchronization listener to avoid subscription quota
conflicts and parallel connect/sync storms.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket
from loguru import logger
from metaapi_cloud_sdk import MetaApi
from metaapi_cloud_sdk.clients.metaapi.synchronization_listener import SynchronizationListener

from app.broker.metaapi import MetaApiConnector
from app.core.config import settings
from app.core.engine import engines

BOT_STATUS_INTERVAL_S = 5
STREAM_IDLE_SEC = 20
CANDLE_INTERVAL_MS = 5000
SNAPSHOT_COUNT = 200

VALID_TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d"})

_account_rpc_locks: dict[str, asyncio.Lock] = {}


def _rpc_lock(account_id: str) -> asyncio.Lock:
    if account_id not in _account_rpc_locks:
        _account_rpc_locks[account_id] = asyncio.Lock()
    return _account_rpc_locks[account_id]


def friendly_metaapi_error(exc: BaseException) -> str:
    msg = str(exc)
    if "subscriptions quota" in msg or "TooManyRequests" in msg:
        return (
            "MetaAPI live subscription limit reached (25 max). "
            "Wait about a minute, keep one chart open, or use HTTP fallback."
        )
    return msg


def _account_to_dict(info: Optional[dict]) -> dict[str, Any]:
    if not info:
        return {
            "balance": 0.0,
            "equity": 0.0,
            "margin": 0.0,
            "free_margin": 0.0,
            "currency": "N/A",
        }
    return {
        "balance": float(info.get("balance", 0)),
        "equity": float(info.get("equity", 0)),
        "margin": float(info.get("margin", 0)),
        "free_margin": float(info.get("freeMargin", 0)),
        "currency": info.get("currency", "USD"),
    }


def _position_to_dict(p: dict) -> dict[str, Any]:
    direction = "BUY" if p.get("type") == "POSITION_TYPE_BUY" else "SELL"
    return {
        "id": str(p.get("id", "")),
        "symbol": p.get("symbol", ""),
        "direction": direction,
        "volume": float(p.get("volume", 0)),
        "open_price": float(p.get("openPrice", 0)),
        "current_price": float(p.get("currentPrice", 0)),
        "stop_loss": p.get("stopLoss"),
        "take_profit": p.get("takeProfit"),
        "profit": float(p.get("profit", 0)),
    }


def _positions_from_terminal_state(terminal_state) -> list[dict[str, Any]]:
    if terminal_state is None:
        return []
    raw = getattr(terminal_state, "positions", None) or []
    return [_position_to_dict(p) for p in raw]


def _account_from_terminal_state(terminal_state) -> dict[str, Any]:
    if terminal_state is None:
        return _account_to_dict(None)
    info = getattr(terminal_state, "accountInformation", None)
    return _account_to_dict(info)


def bot_status_to_dict(user_id: int) -> dict[str, Any]:
    engine = engines.get(user_id)
    if not engine:
        return {
            "running": False,
            "started_at": None,
            "last_tick": None,
            "total_signals": 0,
            "trades_placed": 0,
            "recent_errors": [],
        }
    s = engine.state
    return {
        "running": s.running,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "last_tick": s.last_tick.isoformat() if s.last_tick else None,
        "total_signals": s.total_signals,
        "trades_placed": s.trades_placed,
        "recent_errors": s.errors[-10:],
    }


def get_engine_for_account(account_id: str):
    for engine in engines.values():
        if engine.meta_api_account_id == account_id and engine._broker:
            return engine
    return None


def _candle_time_unix(candle: dict) -> int:
    t = candle.get("time")
    if isinstance(t, datetime):
        if t.tzinfo is None:
            return int(t.replace(tzinfo=timezone.utc).timestamp())
        return int(t.timestamp())
    return int(t)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def meta_candle_to_out(candle: dict) -> Optional[dict[str, Any]]:
    o = _safe_float(candle.get("open"))
    h = _safe_float(candle.get("high"))
    low = _safe_float(candle.get("low"))
    c = _safe_float(candle.get("close"))
    if o is None or h is None or low is None or c is None:
        return None
    return {
        "time": _candle_time_unix(candle),
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": _safe_float(candle.get("tickVolume") or candle.get("volume")) or 0.0,
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


async def fetch_rpc_snapshot(account_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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

    async with _rpc_lock(account_id):
        connector = MetaApiConnector(account_id)
        await connector.connect()
        try:
            info = await connector.get_account_info()
            positions = await connector.get_positions()
        finally:
            await connector.disconnect()
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


async def fetch_candle_snapshot(
    account_id: str, symbol: str, timeframe: str
) -> list[dict[str, Any]]:
    sym = symbol.upper()
    tf = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
    feed = account_hubs.get_chart_cache(account_id, sym, tf)
    if feed:
        return list(feed)

    engine = get_engine_for_account(account_id)
    if engine:
        df = await engine._broker.get_candles(sym, tf, SNAPSHOT_COUNT)
        return dataframe_to_candles(df)

    async with _rpc_lock(account_id):
        connector = MetaApiConnector(account_id)
        await connector.connect()
        try:
            df = await connector.get_candles(sym, tf, SNAPSHOT_COUNT)
        finally:
            await connector.disconnect()
    return dataframe_to_candles(df)


@dataclass
class ChartFeed:
    symbol: str
    timeframe: str
    subscribers: set[WebSocket] = field(default_factory=set)
    ref_count: int = 0
    market_subscribed: bool = False
    last_candles: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.symbol, self.timeframe)


class HubSyncListener(SynchronizationListener):
    def __init__(self, hub: "AccountStreamingHub") -> None:
        self._hub = hub

    async def on_account_information_updated(
        self, instance_index: str, account_information: dict
    ) -> None:
        self._hub._account_data = _account_to_dict(account_information)
        await self._hub._broadcast_dashboard(
            {"type": "account", "account": self._hub._account_data}
        )

    async def on_positions_replaced(self, instance_index: str, positions: list) -> None:
        await self._hub._broadcast_dashboard_positions()

    async def on_position_updated(self, instance_index: str, position: dict) -> None:
        await self._hub._broadcast_dashboard_positions()

    async def on_position_removed(self, instance_index: str, position_id: str) -> None:
        await self._hub._broadcast_dashboard_positions()

    async def on_positions_updated(
        self,
        instance_index: str,
        positions: Any,
        removed_positions_ids: list,
    ) -> None:
        await self._hub._broadcast_dashboard_positions()

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
            feed = self._hub._chart_feeds.get((sym, tf))
            if not feed:
                continue
            out = meta_candle_to_out(raw)
            if out is not None:
                await self._hub._broadcast_chart(feed, {"type": "update", "candle": out})


class AccountStreamingHub:
    """Single streaming connection for one MetaAPI account."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        self._lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._streaming = None
        self._account_meta = None
        self._listener: Optional[HubSyncListener] = None
        self._connected = False
        self._stop_task: Optional[asyncio.Task] = None

        self._dashboard_subscribers: set[WebSocket] = set()
        self._dashboard_user_id: Optional[int] = None
        self._dashboard_ref = 0
        self._bot_task: Optional[asyncio.Task] = None

        self._chart_feeds: dict[tuple[str, str], ChartFeed] = {}
        self._account_data: dict[str, Any] = _account_to_dict(None)
        self._positions_data: list[dict[str, Any]] = []

    def _has_activity(self) -> bool:
        return self._dashboard_ref > 0 or any(f.ref_count > 0 for f in self._chart_feeds.values())

    def _cancel_delayed_stop(self) -> None:
        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
        self._stop_task = None

    async def _delayed_stop(self) -> None:
        try:
            await asyncio.sleep(STREAM_IDLE_SEC)
            async with self._lock:
                if self._has_activity():
                    return
            await self._disconnect()
        except asyncio.CancelledError:
            pass

    def _schedule_delayed_stop(self) -> None:
        self._cancel_delayed_stop()
        self._stop_task = asyncio.create_task(self._delayed_stop())

    async def ensure_connected(self) -> None:
        async with self._connect_lock:
            if self._connected:
                return
            try:
                logger.info(
                    f"Account stream hub connecting | account={self.account_id}"
                )
                api = MetaApi(settings.META_API_TOKEN)
                self._account_meta = await api.metatrader_account_api.get_account(
                    self.account_id
                )
                if self._account_meta.state not in ("DEPLOYING", "DEPLOYED"):
                    await self._account_meta.deploy()
                    await self._account_meta.wait_deployed(60)

                self._streaming = self._account_meta.get_streaming_connection()
                await self._streaming.connect()
                await self._streaming.wait_synchronized()

                self._listener = HubSyncListener(self)
                self._streaming.add_synchronization_listener(self._listener)

                ts = self._streaming.terminal_state
                self._account_data = _account_from_terminal_state(ts)
                self._positions_data = _positions_from_terminal_state(ts)
                if (
                    self._account_data.get("currency") == "N/A"
                    and not self._positions_data
                ):
                    self._account_data, self._positions_data = (
                        await fetch_rpc_snapshot(self.account_id)
                    )

                self._connected = True
                logger.success(
                    f"Account stream hub live | account={self.account_id}"
                )
            except Exception:
                await self._disconnect()
                raise

    async def _disconnect(self) -> None:
        self._cancel_delayed_stop()
        logger.info(f"Account stream hub stopping | account={self.account_id}")
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
            self._bot_task = None

        if self._streaming:
            for feed in list(self._chart_feeds.values()):
                if feed.market_subscribed:
                    try:
                        await self._streaming.unsubscribe_from_market_data(
                            feed.symbol,
                            [{"type": "candles", "timeframe": feed.timeframe}],
                        )
                    except Exception as exc:
                        logger.warning(f"Hub candle unsubscribe failed: {exc}")
                    feed.market_subscribed = False
            try:
                if self._listener:
                    self._streaming.remove_synchronization_listener(self._listener)
            except Exception as exc:
                logger.warning(f"Hub listener remove failed: {exc}")
            try:
                await self._streaming.close()
            except Exception as exc:
                logger.warning(f"Hub stream close failed: {exc}")

        self._streaming = None
        self._listener = None
        self._account_meta = None
        self._connected = False
        self._chart_feeds.clear()
        self._dashboard_subscribers.clear()
        self._dashboard_ref = 0

    async def subscribe_dashboard(self, user_id: int, ws: WebSocket) -> None:
        self._cancel_delayed_stop()
        await self.ensure_connected()
        async with self._lock:
            self._dashboard_subscribers.add(ws)
            self._dashboard_ref += 1
            self._dashboard_user_id = user_id
            first = self._dashboard_ref == 1
        if first:
            await self._send_dashboard_snapshot_all()
            self._bot_task = asyncio.create_task(self._bot_status_loop(user_id))
        else:
            await self._send_dashboard_snapshot(ws, user_id)

    async def unsubscribe_dashboard(self, ws: WebSocket) -> None:
        async with self._lock:
            self._dashboard_subscribers.discard(ws)
            self._dashboard_ref = max(0, self._dashboard_ref - 1)
            empty_dash = self._dashboard_ref == 0
        if empty_dash and self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
            self._bot_task = None
        if not self._has_activity():
            self._schedule_delayed_stop()

    async def subscribe_chart(
        self, symbol: str, timeframe: str, ws: WebSocket
    ) -> None:
        self._cancel_delayed_stop()
        sym = symbol.upper()
        tf = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
        await self.ensure_connected()

        async with self._lock:
            key = (sym, tf)
            feed = self._chart_feeds.get(key)
            if feed is None:
                feed = ChartFeed(symbol=sym, timeframe=tf)
                self._chart_feeds[key] = feed
            feed.subscribers.add(ws)
            feed.ref_count += 1
            first_feed = feed.ref_count == 1

        if first_feed:
            try:
                await self._subscribe_chart_market(feed)
                snapshot = await fetch_candle_snapshot(self.account_id, sym, tf)
                feed.last_candles = snapshot
                await self._broadcast_chart(
                    feed, {"type": "snapshot", "candles": snapshot}
                )
            except Exception:
                async with self._lock:
                    feed.subscribers.discard(ws)
                    feed.ref_count = max(0, feed.ref_count - 1)
                    if feed.ref_count == 0:
                        self._chart_feeds.pop(key, None)
                if not self._has_activity():
                    self._schedule_delayed_stop()
                raise
        else:
            await self._send_chart_snapshot(ws, feed)

    async def unsubscribe_chart(self, symbol: str, timeframe: str, ws: WebSocket) -> None:
        sym = symbol.upper()
        tf = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
        key = (sym, tf)
        async with self._lock:
            feed = self._chart_feeds.get(key)
            if not feed:
                return
            feed.subscribers.discard(ws)
            feed.ref_count = max(0, feed.ref_count - 1)
            remove_feed = feed.ref_count == 0

        if remove_feed:
            await self._unsubscribe_chart_market(feed)
            async with self._lock:
                self._chart_feeds.pop(key, None)

        if not self._has_activity():
            self._schedule_delayed_stop()

    async def _subscribe_chart_market(self, feed: ChartFeed) -> None:
        if not self._streaming or feed.market_subscribed:
            return
        try:
            await self._streaming.subscribe_to_market_data(
                feed.symbol,
                [
                    {
                        "type": "candles",
                        "timeframe": feed.timeframe,
                        "intervalInMilliseconds": CANDLE_INTERVAL_MS,
                    }
                ],
            )
            feed.market_subscribed = True
            logger.info(
                f"Hub candle feed | {feed.symbol} @ {feed.timeframe} | account={self.account_id}"
            )
        except Exception as exc:
            raise RuntimeError(friendly_metaapi_error(exc)) from exc

    async def _unsubscribe_chart_market(self, feed: ChartFeed) -> None:
        if not self._streaming or not feed.market_subscribed:
            return
        try:
            await self._streaming.unsubscribe_from_market_data(
                feed.symbol,
                [{"type": "candles", "timeframe": feed.timeframe}],
            )
        except Exception as exc:
            logger.warning(f"Hub candle unsubscribe failed: {exc}")
        feed.market_subscribed = False

    async def _broadcast_dashboard_positions(self) -> None:
        ts = self._streaming.terminal_state if self._streaming else None
        self._positions_data = _positions_from_terminal_state(ts)
        await self._broadcast_dashboard(
            {"type": "positions", "positions": self._positions_data}
        )

    async def _broadcast_dashboard(self, message: dict) -> None:
        text = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._dashboard_subscribers):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.unsubscribe_dashboard(ws)

    async def _broadcast_chart(self, feed: ChartFeed, message: dict) -> None:
        if message.get("type") == "snapshot" and message.get("candles"):
            feed.last_candles = message["candles"]
        elif message.get("type") == "update" and feed.last_candles:
            candle = message.get("candle")
            if candle:
                t = candle["time"]
                for i, c in enumerate(feed.last_candles):
                    if c["time"] == t:
                        feed.last_candles[i] = candle
                        break
                else:
                    feed.last_candles.append(candle)
                    feed.last_candles.sort(key=lambda x: x["time"])

        text = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(feed.subscribers):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.unsubscribe_chart(feed.symbol, feed.timeframe, ws)

    async def _send_dashboard_snapshot(self, ws: WebSocket, user_id: int) -> None:
        await ws.send_text(
            json.dumps(
                {
                    "type": "snapshot",
                    "account": self._account_data,
                    "positions": self._positions_data,
                    "bot_status": bot_status_to_dict(user_id),
                },
                default=str,
            )
        )

    async def _send_dashboard_snapshot_all(self) -> None:
        uid = self._dashboard_user_id or 0
        msg = {
            "type": "snapshot",
            "account": self._account_data,
            "positions": self._positions_data,
            "bot_status": bot_status_to_dict(uid),
        }
        await self._broadcast_dashboard(msg)

    async def _send_chart_snapshot(self, ws: WebSocket, feed: ChartFeed) -> None:
        try:
            candles = feed.last_candles or await fetch_candle_snapshot(
                self.account_id, feed.symbol, feed.timeframe
            )
            feed.last_candles = candles
            await ws.send_text(json.dumps({"type": "snapshot", "candles": candles}))
        except Exception as exc:
            await ws.send_text(json.dumps({"type": "error", "message": str(exc)}))

    async def _bot_status_loop(self, user_id: int) -> None:
        try:
            while self._dashboard_ref > 0:
                await self._broadcast_dashboard(
                    {
                        "type": "bot_status",
                        "bot_status": bot_status_to_dict(user_id),
                    }
                )
                await asyncio.sleep(BOT_STATUS_INTERVAL_S)
        except asyncio.CancelledError:
            pass

    def get_terminal_account(self) -> dict[str, Any]:
        return dict(self._account_data)

    def get_terminal_positions(self) -> list[dict[str, Any]]:
        return list(self._positions_data)

    def get_chart_cache(
        self, symbol: str, timeframe: str
    ) -> Optional[list[dict[str, Any]]]:
        tf = timeframe if timeframe in VALID_TIMEFRAMES else "1h"
        feed = self._chart_feeds.get((symbol.upper(), tf))
        if feed and feed.last_candles:
            return list(feed.last_candles)
        return None


class AccountStreamingHubManager:
    def __init__(self) -> None:
        self._hubs: dict[str, AccountStreamingHub] = {}
        self._lock = asyncio.Lock()

    async def _get_hub(self, account_id: str) -> AccountStreamingHub:
        async with self._lock:
            if account_id not in self._hubs:
                self._hubs[account_id] = AccountStreamingHub(account_id)
            return self._hubs[account_id]

    async def subscribe_dashboard(
        self, user_id: int, account_id: str, ws: WebSocket
    ) -> AccountStreamingHub:
        hub = await self._get_hub(account_id)
        await hub.subscribe_dashboard(user_id, ws)
        return hub

    async def unsubscribe_dashboard(
        self, user_id: int, account_id: str, ws: WebSocket
    ) -> None:
        async with self._lock:
            hub = self._hubs.get(account_id)
        if hub:
            await hub.unsubscribe_dashboard(ws)
        async with self._lock:
            hub = self._hubs.get(account_id)
            if hub and not hub._has_activity():
                del self._hubs[account_id]

    async def subscribe_chart(
        self,
        user_id: int,
        account_id: str,
        symbol: str,
        timeframe: str,
        ws: WebSocket,
    ) -> AccountStreamingHub:
        hub = await self._get_hub(account_id)
        await hub.subscribe_chart(symbol, timeframe, ws)
        return hub

    async def unsubscribe_chart(
        self,
        user_id: int,
        account_id: str,
        symbol: str,
        timeframe: str,
        ws: WebSocket,
    ) -> None:
        async with self._lock:
            hub = self._hubs.get(account_id)
        if hub:
            await hub.unsubscribe_chart(symbol, timeframe, ws)
        async with self._lock:
            hub = self._hubs.get(account_id)
            if hub and not hub._has_activity():
                del self._hubs[account_id]

    def get_chart_cache(
        self, account_id: str, symbol: str, timeframe: str
    ) -> Optional[list[dict[str, Any]]]:
        hub = self._hubs.get(account_id)
        if hub:
            return hub.get_chart_cache(symbol, timeframe)
        return None

    def get_terminal_snapshot(
        self, account_id: str
    ) -> Optional[tuple[dict[str, Any], list[dict[str, Any]]]]:
        hub = self._hubs.get(account_id)
        if hub and hub._connected:
            acc = hub.get_terminal_account()
            pos = hub.get_terminal_positions()
            if acc.get("currency") != "N/A" or pos:
                return acc, pos
        return None

    async def shutdown(self) -> None:
        async with self._lock:
            hubs = list(self._hubs.values())
            self._hubs.clear()
        for hub in hubs:
            hub._cancel_delayed_stop()
            await hub._disconnect()
        logger.info("All account stream hubs shut down.")


account_hubs = AccountStreamingHubManager()
