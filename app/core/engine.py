"""
Trading engine: per-user instances orchestrating the full cycle on a schedule.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.broker.base import BrokerBase
from app.broker.metaapi import MetaApiConnector
from app.core.executor import execute_signal, sync_closed_positions
from app.core.risk_manager import calculate_risk_levels
from app.core.strategies.dispatcher import run_strategy
from app.core.strategy import Signal

_TF_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


@dataclass
class BotConfig:
    symbol: str = "EURUSD"
    timeframe: str = "1h"
    strategy_name: str = "ema_crossover"   # ema_crossover | rsi_oscillator | macd
    risk_percent: float = 1.0
    max_open_trades: int = 3
    atr_multiplier_sl: float = 1.5
    atr_multiplier_tp: float = 2.5
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0


@dataclass
class BotState:
    running: bool = False
    started_at: Optional[datetime] = None
    last_tick: Optional[datetime] = None
    total_signals: int = 0
    trades_placed: int = 0
    errors: list[str] = field(default_factory=list)


class TradingEngine:
    def __init__(self, user_id: int, meta_api_account_id: str) -> None:
        self.user_id = user_id
        self.meta_api_account_id = meta_api_account_id
        self.config = BotConfig()
        self.state = BotState()
        self._broker: Optional[BrokerBase] = None
        self._scheduler: Optional[AsyncIOScheduler] = None

    async def start(self, config: Optional[BotConfig] = None) -> None:
        if self.state.running:
            logger.warning(f"[user={self.user_id}] Engine already running.")
            return
        if config:
            self.config = config

        self._broker = MetaApiConnector(self.meta_api_account_id)
        await self._broker.connect()

        self._scheduler = AsyncIOScheduler()
        interval = _TF_SECONDS.get(self.config.timeframe, 3600)
        self._scheduler.add_job(
            self._tick, "interval", seconds=interval,
            id="trading_tick", replace_existing=True,
        )
        self._scheduler.start()

        self.state.running = True
        self.state.started_at = datetime.now(timezone.utc)
        self.state.errors.clear()
        logger.success(f"[user={self.user_id}] Bot started | {self.config.symbol} @ {self.config.timeframe}")
        await self._tick()

    async def stop(self) -> None:
        if not self.state.running:
            return
        if self._scheduler and self._scheduler.running:
            self._scheduler.remove_all_jobs()
            self._scheduler.shutdown(wait=False)
        self._scheduler = None
        if self._broker:
            await self._broker.disconnect()
        self.state.running = False
        logger.info(f"[user={self.user_id}] Bot stopped.")

    def update_config(self, config: BotConfig) -> None:
        self.config = config

    async def _tick(self) -> None:
        self.state.last_tick = datetime.now(timezone.utc)
        try:
            await self._run_cycle()
        except Exception as exc:
            msg = f"Tick error: {exc}"
            logger.exception(f"[user={self.user_id}] {msg}")
            self.state.errors.append(msg)

    async def _run_cycle(self) -> None:
        broker = self._broker
        cfg = self.config

        df = await broker.get_candles(cfg.symbol, cfg.timeframe, count=250)
        signal = run_strategy(
            cfg.strategy_name, df,
            ema_fast=cfg.ema_fast, ema_slow=cfg.ema_slow,
            rsi_period=cfg.rsi_period,
            rsi_overbought=cfg.rsi_overbought,
            rsi_oversold=cfg.rsi_oversold,
        )
        self.state.total_signals += 1

        if signal == Signal.NONE:
            logger.debug(f"[user={self.user_id}] No signal this tick.")
            await sync_closed_positions(broker, self.user_id)
            return

        positions = await broker.get_positions()
        open_count = sum(1 for p in positions if p.symbol == cfg.symbol)
        if open_count >= cfg.max_open_trades:
            logger.info(f"[user={self.user_id}] Max open trades reached — skipping.")
            await sync_closed_positions(broker, self.user_id)
            return

        account = await broker.get_account_info()
        risk = calculate_risk_levels(
            df=df, signal_direction=signal.value,
            current_price=df["close"].iloc[-1], equity=account.equity,
            risk_percent=cfg.risk_percent,
            atr_sl_multiplier=cfg.atr_multiplier_sl,
            atr_tp_multiplier=cfg.atr_multiplier_tp,
        )
        if risk is None:
            return

        await execute_signal(broker, signal, risk, cfg.symbol, self.user_id)
        self.state.trades_placed += 1
        await sync_closed_positions(broker, self.user_id)


# ── Per-user engine registry ──────────────────────────────────────────────────
engines: dict[int, TradingEngine] = {}


def get_or_create_engine(user_id: int, meta_api_account_id: str) -> TradingEngine:
    if user_id not in engines:
        engines[user_id] = TradingEngine(user_id, meta_api_account_id)
    return engines[user_id]
