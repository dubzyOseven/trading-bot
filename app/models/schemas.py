from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth schemas ──────────────────────────────────────────────────────────────

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    broker_connected: bool
    mt5_login: Optional[str] = None
    mt5_server: Optional[str] = None
    broker_connected_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Broker schemas ────────────────────────────────────────────────────────────

class BrokerConnectIn(BaseModel):
    mt5_login: str = Field(examples=["123456789"])
    mt5_password: str
    mt5_server: str = Field(examples=["ICMarkets-Demo"])
    account_type: str = Field(default="cloud", examples=["cloud"])
    platform: str = Field(default="mt5", examples=["mt5", "mt4"])


class BrokerStatusOut(BaseModel):
    connected: bool
    mt5_login: Optional[str] = None
    mt5_server: Optional[str] = None
    balance: Optional[float] = None
    equity: Optional[float] = None
    currency: Optional[str] = None


# ── Trade schemas ─────────────────────────────────────────────────────────────

class TradeOut(BaseModel):
    id: int
    order_id: str
    symbol: str
    direction: str
    volume: float
    open_price: float
    close_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    profit: Optional[float] = None
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Bot config schemas ────────────────────────────────────────────────────────

class BotConfigIn(BaseModel):
    symbol: str = Field(default="XAUUSD", examples=["XAUUSD", "EURUSD", "GBPUSD"])
    timeframe: str = Field(default="1m", examples=["1m", "5m", "15m", "1h", "4h", "1d"])
    strategy_name: str = Field(
        default="ema_crossover",
        examples=["ema_crossover", "rsi_oscillator", "macd"],
    )
    risk_percent: float = Field(default=1.0, ge=0.1, le=10.0)
    max_open_trades: int = Field(default=3, ge=1, le=20)
    atr_multiplier_sl: float = Field(default=1.5, ge=0.5, le=5.0)
    atr_multiplier_tp: float = Field(default=2.5, ge=0.5, le=10.0)
    ema_fast: int = Field(default=9, ge=2, le=50)
    ema_slow: int = Field(default=21, ge=5, le=200)
    rsi_period: int = Field(default=14, ge=2, le=50)
    rsi_overbought: float = Field(default=70.0, ge=50.0, le=95.0)
    rsi_oversold: float = Field(default=30.0, ge=5.0, le=50.0)


class BotConfigOut(BotConfigIn):
    pass


# ── Bot status schema ─────────────────────────────────────────────────────────

class BotStatusOut(BaseModel):
    running: bool
    started_at: Optional[datetime] = None
    last_tick: Optional[datetime] = None
    total_signals: int
    trades_placed: int
    recent_errors: list[str]


# ── Position schemas ──────────────────────────────────────────────────────────

class PositionOut(BaseModel):
    id: str
    symbol: str
    direction: str
    volume: float
    open_price: float
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    profit: float


# ── Account schema ────────────────────────────────────────────────────────────

class AccountOut(BaseModel):
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str


# ── Market schemas ────────────────────────────────────────────────────────────

class CandleOut(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class SymbolsOut(BaseModel):
    symbols: list[str]
