import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.dashboard_stream import dashboard_streams
from app.core.security import decode_access_token
from app.db.database import AsyncSessionLocal
from app.models.user import User

router = APIRouter(tags=["Dashboard"])


async def _user_from_ws_token(token: str) -> User:
    user_id = decode_access_token(token)
    if user_id is None:
        raise ValueError("Invalid or expired token.")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("User not found.")
    if not user.broker_connected or not user.meta_api_account_id:
        raise ValueError("No broker connected. Connect your MT5 account first.")
    return user


@router.websocket("/ws/dashboard")
async def ws_dashboard(
    websocket: WebSocket,
    token: str = Query(...),
):
    try:
        user = await _user_from_ws_token(token)
    except ValueError as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc))
        return

    await websocket.accept()

    try:
        await dashboard_streams.subscribe(
            user.id,
            user.meta_api_account_id,
            websocket,
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
    finally:
        await dashboard_streams.unsubscribe(
            user.id,
            user.meta_api_account_id,
            websocket,
        )
