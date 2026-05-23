from datetime import datetime, timezone

from loguru import logger

from app.broker.base import BrokerBase, OrderType
from app.core.risk_manager import RiskLevels
from app.core.strategy import Signal
from app.db.database import AsyncSessionLocal
from app.models.trade import Trade, TradeStatus


async def execute_signal(
    broker: BrokerBase,
    signal: Signal,
    risk: RiskLevels,
    symbol: str,
    user_id: int,
) -> None:
    order_type = OrderType.BUY if signal == Signal.BUY else OrderType.SELL

    placed = await broker.place_order(
        symbol=symbol,
        order_type=order_type,
        volume=risk.volume,
        stop_loss=risk.stop_loss,
        take_profit=risk.take_profit,
    )

    # Try to get actual fill price from broker history (more reliable than order result)
    open_price = placed.price
    if not open_price or open_price == 0.0:
        fill = await broker.get_fill_price(placed.order_id)
        if fill:
            open_price = fill

    async with AsyncSessionLocal() as session:
        async with session.begin():
            trade = Trade(
                user_id=user_id,
                order_id=placed.order_id,
                symbol=symbol,
                direction=order_type.value,
                volume=placed.volume,
                open_price=open_price,
                stop_loss=placed.stop_loss,
                take_profit=placed.take_profit,
                status=TradeStatus.OPEN,
                opened_at=datetime.now(timezone.utc),
            )
            session.add(trade)

    logger.success(
        f"[user={user_id}] Trade recorded | {order_type} {risk.volume} {symbol} "
        f"@ {open_price} SL={risk.stop_loss} TP={risk.take_profit}"
    )


async def sync_closed_positions(broker: BrokerBase, user_id: int) -> None:
    """Mark DB trades as CLOSED and populate close_price + profit if no longer open."""
    open_positions = await broker.get_positions()
    open_ids = {p.id for p in open_positions}

    async with AsyncSessionLocal() as session:
        async with session.begin():
            from sqlalchemy import select
            result = await session.execute(
                select(Trade).where(
                    Trade.status == TradeStatus.OPEN,
                    Trade.user_id == user_id,
                )
            )
            open_trades = result.scalars().all()

            for trade in open_trades:
                if trade.order_id not in open_ids:
                    # Fetch close price and realized profit from broker deal history
                    deal = await broker.get_deal_result(trade.order_id)
                    if deal:
                        trade.close_price = deal["close_price"]
                        trade.profit = deal["profit"]

                    trade.status = TradeStatus.CLOSED
                    trade.closed_at = datetime.now(timezone.utc)
                    logger.info(
                        f"[user={user_id}] Trade {trade.order_id} CLOSED | "
                        f"close_price={trade.close_price} profit={trade.profit}"
                    )
