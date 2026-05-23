from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_connected_user
from app.core.engine import BotConfig, engines, get_or_create_engine
from app.models.schemas import BotStatusOut
from app.models.user import User

router = APIRouter(prefix="/bot", tags=["Bot Control"])


@router.post("/start", status_code=status.HTTP_200_OK, summary="Start the trading bot")
async def start_bot(user: User = Depends(get_connected_user)):
    engine = get_or_create_engine(user.id, user.meta_api_account_id)
    if engine.state.running:
        raise HTTPException(status_code=409, detail="Bot is already running.")
    await engine.start()
    return {"message": "Bot started."}


@router.post("/stop", status_code=status.HTTP_200_OK, summary="Stop the trading bot")
async def stop_bot(user: User = Depends(get_connected_user)):
    engine = engines.get(user.id)
    if not engine or not engine.state.running:
        raise HTTPException(status_code=409, detail="Bot is not running.")
    await engine.stop()
    return {"message": "Bot stopped."}


@router.get("/status", response_model=BotStatusOut, summary="Get bot status")
async def bot_status(user: User = Depends(get_connected_user)):
    engine = engines.get(user.id)
    if not engine:
        return BotStatusOut(running=False, total_signals=0, trades_placed=0, recent_errors=[])
    s = engine.state
    return BotStatusOut(
        running=s.running,
        started_at=s.started_at,
        last_tick=s.last_tick,
        total_signals=s.total_signals,
        trades_placed=s.trades_placed,
        recent_errors=s.errors[-10:],
    )
