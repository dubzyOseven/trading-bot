"""
Live dashboard streaming: MetaAPI account/position updates + in-memory bot status.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import WebSocket
from loguru import logger
from metaapi_cloud_sdk import MetaApi
from metaapi_cloud_sdk.clients.metaapi.synchronization_listener import SynchronizationListener

from app.broker.metaapi import MetaApiConnector
from app.core.chart_stream import friendly_metaapi_error
from app.core.config import settings
from app.core.engine import engines

BOT_STATUS_INTERVAL_S = 5
STREAM_IDLE_SEC = 20


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


async def fetch_rpc_snapshot(account_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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


class DashboardStreamListener(SynchronizationListener):
    def __init__(self, session: "DashboardStreamSession") -> None:
        self._session = session

    async def on_account_information_updated(
        self, instance_index: str, account_information: dict
    ) -> None:
        self._session._account_data = _account_to_dict(account_information)
        await self._session.broadcast(
            {"type": "account", "account": self._session._account_data}
        )

    async def on_positions_replaced(
        self, instance_index: str, positions: list
    ) -> None:
        await self._session._broadcast_positions()

    async def on_position_updated(
        self, instance_index: str, position: dict
    ) -> None:
        await self._session._broadcast_positions()

    async def on_position_removed(self, instance_index: str, position_id: str) -> None:
        await self._session._broadcast_positions()

    async def on_positions_updated(
        self,
        instance_index: str,
        positions: Any,
        removed_positions_ids: list,
    ) -> None:
        await self._session._broadcast_positions()


class DashboardStreamSession:
    def __init__(self, user_id: int, account_id: str) -> None:
        self.user_id = user_id
        self.account_id = account_id
        self.subscribers: set[WebSocket] = set()
        self._ref_count = 0
        self._lock = asyncio.Lock()
        self._streaming = None
        self._listener: Optional[DashboardStreamListener] = None
        self._account_meta = None
        self._started = False
        self._bot_task: Optional[asyncio.Task] = None
        self._stop_task: Optional[asyncio.Task] = None
        self._account_data: dict[str, Any] = _account_to_dict(None)
        self._positions_data: list[dict[str, Any]] = []

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
                logger.exception(f"Dashboard stream start failed: {exc}")
                await self._stop_stream()
                err_msg = friendly_metaapi_error(exc)
                await self.broadcast({"type": "error", "message": err_msg})
                await self._release_subscriber(ws)
                raise RuntimeError(err_msg) from exc
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

    async def _read_terminal_snapshot(self) -> None:
        ts = self._streaming.terminal_state if self._streaming else None
        self._account_data = _account_from_terminal_state(ts)
        self._positions_data = _positions_from_terminal_state(ts)
        if self._account_data.get("currency") == "N/A" and not self._positions_data:
            self._account_data, self._positions_data = await fetch_rpc_snapshot(
                self.account_id
            )

    async def _broadcast_positions(self) -> None:
        ts = self._streaming.terminal_state if self._streaming else None
        self._positions_data = _positions_from_terminal_state(ts)
        await self.broadcast({"type": "positions", "positions": self._positions_data})

    async def _start_stream(self) -> None:
        logger.info(f"[user={self.user_id}] Starting dashboard stream")
        api = MetaApi(settings.META_API_TOKEN)
        self._account_meta = await api.metatrader_account_api.get_account(self.account_id)

        if self._account_meta.state not in ("DEPLOYING", "DEPLOYED"):
            await self._account_meta.deploy()
            await self._account_meta.wait_deployed(60)

        self._streaming = self._account_meta.get_streaming_connection()
        await self._streaming.connect()
        await self._streaming.wait_synchronized()

        self._listener = DashboardStreamListener(self)
        self._streaming.add_synchronization_listener(self._listener)

        await self._read_terminal_snapshot()
        snapshot = {
            "type": "snapshot",
            "account": self._account_data,
            "positions": self._positions_data,
            "bot_status": bot_status_to_dict(self.user_id),
        }
        await self.broadcast(snapshot)

        self._bot_task = asyncio.create_task(self._bot_status_loop())
        logger.success(f"[user={self.user_id}] Dashboard stream live")

    async def _bot_status_loop(self) -> None:
        try:
            while self._started:
                await self.broadcast(
                    {
                        "type": "bot_status",
                        "bot_status": bot_status_to_dict(self.user_id),
                    }
                )
                await asyncio.sleep(BOT_STATUS_INTERVAL_S)
        except asyncio.CancelledError:
            pass

    async def _stop_stream(self) -> None:
        self._cancel_delayed_stop()
        logger.info(f"[user={self.user_id}] Stopping dashboard stream")
        self._started = False
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
            self._bot_task = None
        if self._streaming:
            try:
                if self._listener:
                    self._streaming.remove_synchronization_listener(self._listener)
            except Exception as exc:
                logger.warning(f"Dashboard stream listener remove failed: {exc}")
            try:
                await self._streaming.close()
            except Exception as exc:
                logger.warning(f"Dashboard stream close failed: {exc}")
        self._streaming = None
        self._listener = None
        self._account_meta = None

    async def _send_snapshot(self, ws: WebSocket) -> None:
        await ws.send_text(
            json.dumps(
                {
                    "type": "snapshot",
                    "account": self._account_data,
                    "positions": self._positions_data,
                    "bot_status": bot_status_to_dict(self.user_id),
                }
            )
        )

    async def broadcast(self, message: dict) -> None:
        text = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in list(self.subscribers):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.remove_subscriber(ws)


class DashboardStreamManager:
    def __init__(self) -> None:
        self._sessions: dict[tuple[int, str], DashboardStreamSession] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, user_id: int, account_id: str, ws: WebSocket
    ) -> DashboardStreamSession:
        key = (user_id, account_id)
        async with self._lock:
            if key not in self._sessions:
                self._sessions[key] = DashboardStreamSession(user_id, account_id)
            session = self._sessions[key]
        await session.add_subscriber(ws)
        return session

    async def unsubscribe(self, user_id: int, account_id: str, ws: WebSocket) -> None:
        key = (user_id, account_id)
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
        logger.info("All dashboard streams shut down.")


dashboard_streams = DashboardStreamManager()
