from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import auth, bot, broker, config, dashboard, market, trades
from app.core.config import settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting trading-bot API | env={settings.APP_ENV}")
    # Ensure both models are imported before create_all
    import app.models.user  # noqa: F401
    import app.models.trade  # noqa: F401
    await init_db()
    yield
    from app.core.chart_stream import chart_streams
    from app.core.dashboard_stream import dashboard_streams
    from app.core.engine import engines

    for engine in list(engines.values()):
        if engine.state.running:
            await engine.stop()
    await chart_streams.shutdown()
    await dashboard_streams.shutdown()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Forex Trading Bot API",
    description="Multi-user MT5 forex trading bot platform via MetaAPI.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(broker.router, prefix=API_PREFIX)
app.include_router(bot.router, prefix=API_PREFIX)
app.include_router(trades.router, prefix=API_PREFIX)
app.include_router(config.router, prefix=API_PREFIX)
app.include_router(market.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
