from __future__ import annotations

from typing import Optional

import pandas as pd
from loguru import logger
from metaapi_cloud_sdk import MetaApi

from app.broker.base import (
    AccountInfo,
    BrokerBase,
    OrderType,
    PlacedOrder,
    Position,
)
from app.core.config import settings

# MetaAPI timeframe mapping
_TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class MetaApiConnector(BrokerBase):
    def __init__(self, account_id: Optional[str] = None) -> None:
        self._api: Optional[MetaApi] = None
        self._connection = None
        self._account = None
        self._account_id = account_id or settings.META_API_ACCOUNT_ID

    async def connect(self) -> None:
        logger.info(f"Connecting to MetaAPI (account={self._account_id})…")
        self._api = MetaApi(settings.META_API_TOKEN)
        self._account = await self._api.metatrader_account_api.get_account(
            self._account_id
        )

        if self._account.state not in ("DEPLOYING", "DEPLOYED"):
            await self._account.deploy()
            await self._account.wait_deployed(60)

        self._connection = self._account.get_rpc_connection()
        await self._connection.connect()
        await self._connection.wait_synchronized()
        logger.success("MetaAPI connected and synchronized.")

    async def disconnect(self) -> None:
        if self._connection:
            await self._connection.close()
            logger.info("MetaAPI connection closed.")

    async def get_account_info(self) -> AccountInfo:
        info = await self._connection.get_account_information()
        return AccountInfo(
            balance=info["balance"],
            equity=info["equity"],
            margin=info.get("margin", 0.0),
            free_margin=info.get("freeMargin", 0.0),
            currency=info.get("currency", "USD"),
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> pd.DataFrame:
        tf = _TIMEFRAME_MAP.get(timeframe, "1h")
        candles = await self._account.get_historical_candles(symbol, tf, None, count)
        records = [
            {
                "time": c["time"],
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c.get("tickVolume", 0),
            }
            for c in candles
        ]
        df = pd.DataFrame(records)
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time").sort_index()
        return df

    async def get_positions(self) -> list[Position]:
        raw = await self._connection.get_positions()
        result = []
        for p in raw:
            result.append(
                Position(
                    id=p["id"],
                    symbol=p["symbol"],
                    order_type=OrderType.BUY if p["type"] == "POSITION_TYPE_BUY" else OrderType.SELL,
                    volume=p["volume"],
                    open_price=p["openPrice"],
                    current_price=p["currentPrice"],
                    stop_loss=p.get("stopLoss"),
                    take_profit=p.get("takeProfit"),
                    profit=p.get("profit", 0.0),
                    open_time=str(p.get("time", "")),
                )
            )
        return result

    async def place_order(
        self,
        symbol: str,
        order_type: OrderType,
        volume: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "trading-bot",
    ) -> PlacedOrder:
        options: dict = {"comment": comment}

        sl = float(stop_loss) if stop_loss is not None else None
        tp = float(take_profit) if take_profit is not None else None
        vol = float(volume)

        if order_type == OrderType.BUY:
            result = await self._connection.create_market_buy_order(
                symbol, vol, sl, tp, options
            )
        else:
            result = await self._connection.create_market_sell_order(
                symbol, vol, sl, tp, options
            )

        logger.info(f"Order placed: {order_type} {volume} {symbol} → id={result.get('orderId')}")
        return PlacedOrder(
            order_id=str(result.get("orderId", "")),
            symbol=symbol,
            order_type=order_type,
            volume=volume,
            price=result.get("openPrice", 0.0),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    async def close_position(self, position_id: str) -> bool:
        try:
            await self._connection.close_position(position_id)
            logger.info(f"Position {position_id} closed.")
            return True
        except Exception as exc:
            logger.error(f"Failed to close position {position_id}: {exc}")
            return False

    async def get_fill_price(self, order_id: str) -> Optional[float]:
        """Fetch the actual fill price from MetaAPI history orders."""
        try:
            orders = await self._connection.get_history_orders_by_ticket(order_id)
            for o in orders:
                price = o.get("openPrice") or o.get("currentPrice")
                if price:
                    return float(price)
        except Exception as exc:
            logger.debug(f"Could not fetch fill price for order {order_id}: {exc}")
        return None

    async def get_deal_result(self, order_id: str) -> Optional[dict]:
        """Fetch close price and profit from MetaAPI deals for a closed trade."""
        try:
            deals = await self._connection.get_deals_by_ticket(order_id)
            # Deals are ordered oldest first; the last deal is the close deal
            for deal in reversed(deals):
                deal_type = deal.get("type", "")
                # OUT deals are closing deals
                if "OUT" in deal_type or deal.get("entryType") == "DEAL_ENTRY_OUT":
                    return {
                        "close_price": float(deal.get("price", 0.0)),
                        "profit": float(deal.get("profit", 0.0)),
                    }
            # Fallback: use last deal regardless of type
            if deals:
                last = deals[-1]
                return {
                    "close_price": float(last.get("price", 0.0)),
                    "profit": float(last.get("profit", 0.0)),
                }
        except Exception as exc:
            logger.debug(f"Could not fetch deal result for order {order_id}: {exc}")
        return None
