import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.api.deps import get_connected_user
from app.core.account_stream_hub import account_hubs
from app.core.broker_access import get_candles_df, get_symbols_list
from app.core.chart_stream import VALID_TIMEFRAMES, chart_streams
from app.core.security import decode_access_token
from app.db.database import AsyncSessionLocal
from app.models.schemas import CandleOut, SymbolsOut
from app.models.user import User

router = APIRouter(tags=["Market"])

_DEFAULT_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "AUDJPY", "AUDNZD", "AUDCAD", "CADJPY", "CHFJPY", "NZDJPY", "NZDCAD",
    "XAUUSD", "XAGUSD",
]

_VALID_TIMEFRAMES = VALID_TIMEFRAMES


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


@router.websocket("/ws/market/candles")
async def ws_market_candles(
    websocket: WebSocket,
    token: str = Query(...),
    symbol: str = Query(default="EURUSD"),
    timeframe: str = Query(default="1h"),
):
    try:
        user = await _user_from_ws_token(token)
    except ValueError as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc))
        return

    await websocket.accept()
    tf = timeframe if timeframe in _VALID_TIMEFRAMES else "1h"
    sym = symbol.upper()

    try:
        await chart_streams.subscribe(
            user.id,
            user.meta_api_account_id,
            sym,
            tf,
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
        await chart_streams.unsubscribe(
            user.id,
            user.meta_api_account_id,
            sym,
            tf,
            websocket,
        )


@router.get("/market/symbols", response_model=SymbolsOut, summary="List tradable symbols")
async def get_symbols(user: User = Depends(get_connected_user)):
    symbols = await get_symbols_list(user.meta_api_account_id)
    return SymbolsOut(symbols=symbols or _DEFAULT_SYMBOLS)


@router.get("/market/candles", response_model=list[CandleOut], summary="Get OHLCV candles")
async def get_candles(
    symbol: str = Query(default="EURUSD", examples=["EURUSD", "GBPUSD"]),
    timeframe: str = Query(default="1h", examples=["1m", "5m", "15m", "1h", "4h", "1d"]),
    count: int = Query(default=200, ge=10, le=500),
    user: User = Depends(get_connected_user),
):
    tf = timeframe if timeframe in _VALID_TIMEFRAMES else "1h"
    sym = symbol.upper()
    cached = account_hubs.get_chart_cache(user.meta_api_account_id, sym, tf)
    if cached:
        return [CandleOut(**c) for c in cached[-count:]]

    df = await get_candles_df(user.meta_api_account_id, sym, tf, count)
    candles: list[CandleOut] = []
    for ts, row in df.iterrows():
        candles.append(
            CandleOut(
                time=int(ts.timestamp()),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )
    return candles
