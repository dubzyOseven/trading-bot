from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import pandas as pd


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str


@dataclass
class Position:
    id: str
    symbol: str
    order_type: OrderType
    volume: float
    open_price: float
    current_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    profit: float
    open_time: str


@dataclass
class PlacedOrder:
    order_id: str
    symbol: str
    order_type: OrderType
    volume: float
    price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_id: Optional[str] = None


class BrokerBase(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to broker."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection gracefully."""

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Return current account balance, equity, margin."""

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 200,
    ) -> pd.DataFrame:
        """Return OHLCV dataframe with columns: open, high, low, close, volume."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Return all currently open positions."""

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        order_type: OrderType,
        volume: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "trading-bot",
    ) -> PlacedOrder:
        """Place a market order."""

    @abstractmethod
    async def close_position(self, position_id: str) -> bool:
        """Close an open position by ID."""

    @abstractmethod
    async def get_fill_price(self, order_id: str) -> Optional[float]:
        """Return the actual fill price for a placed order, or None if unavailable."""

    @abstractmethod
    async def get_deal_result(
        self, order_id: str, position_id: Optional[str] = None
    ) -> Optional[dict]:
        """Return {'close_price': float, 'profit': float} for a closed trade, or None."""
