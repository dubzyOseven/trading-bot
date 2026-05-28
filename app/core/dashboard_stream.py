"""
Live dashboard streaming — delegates to shared account stream hub.
"""

from __future__ import annotations

from fastapi import WebSocket
from loguru import logger

from app.core.account_stream_hub import (
    account_hubs,
    bot_status_to_dict,
    fetch_rpc_snapshot,
    friendly_metaapi_error,
)

# Re-export for routes/tests that import from here
__all__ = [
    "bot_status_to_dict",
    "fetch_rpc_snapshot",
    "friendly_metaapi_error",
    "dashboard_streams",
]


class DashboardStreamManager:
    async def subscribe(
        self, user_id: int, account_id: str, ws: WebSocket
    ) -> None:
        try:
            await account_hubs.subscribe_dashboard(user_id, account_id, ws)
        except Exception as exc:
            logger.exception(f"Dashboard stream subscribe failed: {exc}")
            raise RuntimeError(friendly_metaapi_error(exc)) from exc

    async def unsubscribe(self, user_id: int, account_id: str, ws: WebSocket) -> None:
        await account_hubs.unsubscribe_dashboard(user_id, account_id, ws)

    async def shutdown(self) -> None:
        await account_hubs.shutdown()


dashboard_streams = DashboardStreamManager()
