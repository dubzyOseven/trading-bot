from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from app.broker.base import BrokerBase, OrderType, Position
from app.core.risk_manager import RiskLevels
from app.core.strategy import Signal
from app.db.database import AsyncSessionLocal
from app.models.trade import Trade, TradeStatus


def _position_is_open(trade: Trade, open_position_ids: set[str]) -> bool:
    if trade.position_id and str(trade.position_id) in open_position_ids:
        return True
    if str(trade.order_id) in open_position_ids:
        return True
    return False


def _tracked_ids(trades: list[Trade]) -> set[str]:
    ids: set[str] = set()
    for trade in trades:
        if trade.position_id:
            ids.add(str(trade.position_id))
        ids.add(str(trade.order_id))
    return ids


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

    if not placed.order_id:
        logger.error(f"[user={user_id}] Broker returned no order/position id — trade not recorded.")
        return

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
                position_id=placed.position_id,
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
        f"@ {open_price} SL={risk.stop_loss} TP={risk.take_profit} "
        f"order_id={placed.order_id} position_id={placed.position_id}"
    )


async def _backfill_open_position(
    session,
    position: Position,
    user_id: int,
) -> None:
    session.add(
        Trade(
            user_id=user_id,
            order_id=str(position.id),
            position_id=str(position.id),
            symbol=position.symbol,
            direction=position.order_type.value,
            volume=position.volume,
            open_price=position.open_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            status=TradeStatus.OPEN,
            opened_at=datetime.now(timezone.utc),
        )
    )
    logger.info(
        f"[user={user_id}] Backfilled trade history for open position {position.id} {position.symbol}"
    )


async def sync_closed_positions(broker: BrokerBase, user_id: int) -> None:
    """Sync DB trades with broker: close finished trades, backfill missing open ones."""
    open_positions = await broker.get_positions()
    open_position_ids = {str(p.id) for p in open_positions}

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(Trade).where(
                    Trade.status == TradeStatus.OPEN,
                    Trade.user_id == user_id,
                )
            )
            open_trades = list(result.scalars().all())
            tracked = _tracked_ids(open_trades)

            for trade in open_trades:
                if _position_is_open(trade, open_position_ids):
                    continue

                deal = await broker.get_deal_result(
                    trade.order_id, position_id=trade.position_id
                )
                if deal:
                    trade.close_price = deal["close_price"]
                    trade.profit = deal["profit"]

                trade.status = TradeStatus.CLOSED
                trade.closed_at = datetime.now(timezone.utc)
                logger.info(
                    f"[user={user_id}] Trade {trade.order_id} CLOSED | "
                    f"close_price={trade.close_price} profit={trade.profit}"
                )

            for position in open_positions:
                pid = str(position.id)
                if pid in tracked:
                    continue
                await _backfill_open_position(session, position, user_id)
