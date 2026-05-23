# Forex Trading Bot

An automated MT5 forex trading bot with a FastAPI REST interface, deployable on any Linux server via MetaAPI.

## Architecture

```
FastAPI (REST API)
    └── Trading Engine (APScheduler loop)
            ├── Strategy       → EMA crossover + RSI filter
            ├── Risk Manager   → ATR-based SL/TP + position sizing
            ├── Executor       → Places orders, persists to DB
            └── MetaAPI        → MT5 broker connector (cloud)
```

## Quick Start

### 1. Prerequisites

- MetaAPI account → https://metaapi.cloud (free tier available)
- MT5 broker account connected to MetaAPI
- Docker & Docker Compose

### 2. Configure

```bash
cp .env.example .env
# Edit .env and fill in:
#   META_API_TOKEN      — from https://app.metaapi.cloud/token
#   META_API_ACCOUNT_ID — your MT5 account ID in MetaAPI
#   API_KEY             — any long random string for securing the API
```

### 3. Run

```bash
docker compose up --build
```

API will be available at `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

### 4. Start the bot

```bash
curl -X POST http://localhost:8000/api/v1/bot/start \
  -H "X-API-Key: your_api_key"
```

---

## API Endpoints

All endpoints require `X-API-Key` header.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/bot/start` | Start the trading bot |
| `POST` | `/api/v1/bot/stop` | Stop the trading bot |
| `GET` | `/api/v1/bot/status` | Running state, signals, trades count |
| `GET` | `/api/v1/positions` | Live open positions from broker |
| `GET` | `/api/v1/history` | Closed trade history from DB |
| `GET` | `/api/v1/account` | Broker account balance & equity |
| `GET` | `/api/v1/config` | Current strategy configuration |
| `PUT` | `/api/v1/config` | Update strategy parameters live |
| `GET` | `/health` | Health check (no auth) |

---

## Strategy: EMA Crossover + RSI Filter

**BUY** when:
- Fast EMA (9) crosses **above** Slow EMA (21)
- RSI (14) is **below** 70 (not overbought)

**SELL** when:
- Fast EMA (9) crosses **below** Slow EMA (21)
- RSI (14) is **above** 30 (not oversold)

All parameters are configurable via `PUT /api/v1/config`.

---

## Risk Management

- **Position size**: `equity × risk% / (pip_distance × pip_value_per_lot)`
- **Stop-loss**: `ATR × sl_multiplier` pips from entry
- **Take-profit**: `ATR × tp_multiplier` pips from entry
- **Max open trades**: configurable cap per symbol

Default: 1% risk per trade, 1.5× ATR stop-loss, 2.5× ATR take-profit.

---

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `symbol` | `EURUSD` | Forex pair |
| `timeframe` | `1h` | Candle timeframe |
| `risk_percent` | `1.0` | % of equity risked per trade |
| `max_open_trades` | `3` | Max simultaneous open trades |
| `atr_multiplier_sl` | `1.5` | ATR multiplier for stop-loss |
| `atr_multiplier_tp` | `2.5` | ATR multiplier for take-profit |
| `ema_fast` | `9` | Fast EMA period |
| `ema_slow` | `21` | Slow EMA period |
| `rsi_period` | `14` | RSI period |

---

## Local Development (no Docker)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values

# Start Postgres separately, then:
uvicorn app.main:app --reload
```

## Tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

---

## Deployment (Railway / Render)

1. Push this repo to GitHub
2. Connect to Railway/Render
3. Add environment variables from `.env`
4. Add a Postgres plugin/database
5. Deploy — done

---

## Important Warnings

- **Always test on a paper/demo account first** before connecting real money.
- Past strategy performance does not guarantee future results.
- Monitor the bot regularly; automated systems can incur losses rapidly.
