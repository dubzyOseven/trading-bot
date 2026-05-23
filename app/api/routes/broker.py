"""
Broker provisioning: creates a MetaAPI account on behalf of the user,
stores their encrypted MT5 credentials, and manages connection lifecycle.
"""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import decrypt, encrypt
from app.db.database import get_db
from app.models.schemas import BrokerConnectIn, BrokerStatusOut
from app.models.user import User

router = APIRouter(prefix="/broker", tags=["Broker"])

_PROVISIONING_URL = (
    "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts"
)


@router.post("/connect", response_model=BrokerStatusOut)
async def connect_broker(
    body: BrokerConnectIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.broker_connected and user.meta_api_account_id:
        raise HTTPException(status_code=409, detail="Broker already connected. Disconnect first.")

    logger.info(f"Provisioning MetaAPI account for user {user.id} | server={body.mt5_server}")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _PROVISIONING_URL,
            headers={"auth-token": settings.META_API_TOKEN},
            json={
                "login": str(body.mt5_login),
                "password": body.mt5_password,
                "name": f"user_{user.id}_{body.mt5_login}",
                "server": body.mt5_server,
                "platform": body.platform,
                "magic": 0,
                "type": body.account_type,
            },
        )

    if resp.status_code not in (200, 201):
        logger.error(f"MetaAPI provisioning failed: {resp.text}")
        raise HTTPException(
            status_code=502,
            detail=f"MetaAPI provisioning failed: {resp.json().get('message', resp.text)}",
        )

    account_id = resp.json()["id"]
    logger.info(f"MetaAPI account provisioned: {account_id}")

    # Deploy the account so MetaAPI starts syncing it
    from metaapi_cloud_sdk import MetaApi
    api = MetaApi(settings.META_API_TOKEN)
    account = await api.metatrader_account_api.get_account(account_id)
    if account.state not in ("DEPLOYING", "DEPLOYED"):
        await account.deploy()
        await account.wait_deployed(60)

    # Persist encrypted credentials immediately — don't block on WebSocket sync.
    # The WebSocket connection is established when the bot starts, not here.
    user.mt5_login = str(body.mt5_login)
    user.mt5_server = body.mt5_server
    user.mt5_password_encrypted = encrypt(body.mt5_password)
    user.meta_api_account_id = account_id
    user.broker_connected = True
    user.broker_connected_at = datetime.now(timezone.utc)
    await db.commit()

    logger.success(f"Broker connected for user {user.id} | account_id={account_id}")
    return BrokerStatusOut(
        connected=True,
        mt5_login=user.mt5_login,
        mt5_server=user.mt5_server,
    )


@router.delete("/disconnect")
async def disconnect_broker(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.broker_connected:
        raise HTTPException(status_code=409, detail="No broker connected.")

    # Stop user's bot if running
    from app.core.engine import engines
    if user.id in engines:
        await engines[user.id].stop()
        del engines[user.id]

    # Undeploy MetaAPI account
    if user.meta_api_account_id:
        try:
            from metaapi_cloud_sdk import MetaApi
            api = MetaApi(settings.META_API_TOKEN)
            account = await api.metatrader_account_api.get_account(user.meta_api_account_id)
            await account.undeploy()
        except Exception as exc:
            logger.warning(f"Failed to undeploy MetaAPI account: {exc}")

    user.broker_connected = False
    user.meta_api_account_id = None
    user.mt5_password_encrypted = None
    user.broker_connected_at = None
    await db.commit()

    return {"message": "Broker disconnected."}


@router.get("/status", response_model=BrokerStatusOut)
async def broker_status(
    user: User = Depends(get_current_user),
):
    if not user.broker_connected or not user.meta_api_account_id:
        return BrokerStatusOut(connected=False)

    try:
        from metaapi_cloud_sdk import MetaApi
        api = MetaApi(settings.META_API_TOKEN)
        account = await api.metatrader_account_api.get_account(user.meta_api_account_id)
        conn = account.get_rpc_connection()
        await conn.connect()
        await conn.wait_synchronized()
        info = await conn.get_account_information()
        await conn.close()
        return BrokerStatusOut(
            connected=True,
            mt5_login=user.mt5_login,
            mt5_server=user.mt5_server,
            balance=info["balance"],
            equity=info["equity"],
            currency=info.get("currency", "USD"),
        )
    except Exception as exc:
        logger.error(f"Broker status check failed for user {user.id}: {exc}")
        return BrokerStatusOut(connected=False, mt5_login=user.mt5_login, mt5_server=user.mt5_server)
