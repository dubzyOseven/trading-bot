from fastapi import APIRouter, Depends

from app.api.deps import get_connected_user
from app.core.engine import BotConfig, engines, get_or_create_engine
from app.models.schemas import BotConfigIn, BotConfigOut
from app.models.user import User

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.get("", response_model=BotConfigOut, summary="Get current bot configuration")
async def get_config(user: User = Depends(get_connected_user)):
    engine = get_or_create_engine(user.id, user.meta_api_account_id)
    c = engine.config
    return BotConfigOut(
        symbol=c.symbol,
        timeframe=c.timeframe,
        strategy_name=c.strategy_name,
        risk_percent=c.risk_percent,
        max_open_trades=c.max_open_trades,
        atr_multiplier_sl=c.atr_multiplier_sl,
        atr_multiplier_tp=c.atr_multiplier_tp,
        ema_fast=c.ema_fast,
        ema_slow=c.ema_slow,
        rsi_period=c.rsi_period,
        rsi_overbought=c.rsi_overbought,
        rsi_oversold=c.rsi_oversold,
    )


@router.put("", response_model=BotConfigOut, summary="Update bot configuration (live)")
async def update_config(body: BotConfigIn, user: User = Depends(get_connected_user)):
    engine = get_or_create_engine(user.id, user.meta_api_account_id)
    engine.update_config(BotConfig(
        symbol=body.symbol,
        timeframe=body.timeframe,
        strategy_name=body.strategy_name,
        risk_percent=body.risk_percent,
        max_open_trades=body.max_open_trades,
        atr_multiplier_sl=body.atr_multiplier_sl,
        atr_multiplier_tp=body.atr_multiplier_tp,
        ema_fast=body.ema_fast,
        ema_slow=body.ema_slow,
        rsi_period=body.rsi_period,
        rsi_overbought=body.rsi_overbought,
        rsi_oversold=body.rsi_oversold,
    ))
    return body
