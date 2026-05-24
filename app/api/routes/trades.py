from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import get_connected_user, get_current_user
from app.core.engine import engines
from app.db.database import get_db
from app.models.schemas import AccountOut, PositionOut, TradeOut
from app.models.trade import Trade, TradeStatus
from app.models.user import User

router = APIRouter(tags=["Trades & Positions"])


@router.get("/positions", response_model=list[PositionOut], summary="Get open positions")
async def get_positions(user: User = Depends(get_connected_user)):
    engine = engines.get(user.id)
    if not engine or not engine._broker:
        return []
    positions = await engine._broker.get_positions()
    return [
        PositionOut(
            id=p.id, symbol=p.symbol, direction=p.order_type.value,
            volume=p.volume, open_price=p.open_price, current_price=p.current_price,
            stop_loss=p.stop_loss, take_profit=p.take_profit, profit=p.profit,
        )
        for p in positions
    ]


@router.get("/history", response_model=list[TradeOut], summary="Get trade history")
async def get_history(
    symbol: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    query = (
        select(Trade)
        .where(Trade.user_id == user.id)
        .order_by(Trade.opened_at.desc())
        .limit(limit)
    )
    if symbol:
        query = query.where(Trade.symbol == symbol.upper())
    if status:
        try:
            query = query.where(Trade.status == TradeStatus(status.upper()))
        except ValueError:
            return []
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/account", response_model=AccountOut, summary="Get broker account info")
async def get_account(user: User = Depends(get_connected_user)):
    engine = engines.get(user.id)
    if not engine or not engine._broker:
        return AccountOut(balance=0, equity=0, margin=0, free_margin=0, currency="N/A")
    info = await engine._broker.get_account_info()
    return AccountOut(
        balance=info.balance, equity=info.equity,
        margin=info.margin, free_margin=info.free_margin, currency=info.currency,
    )
