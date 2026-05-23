from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # MT5 broker credentials (encrypted at rest)
    mt5_login: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mt5_server: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    mt5_password_encrypted: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # MetaAPI provisioned account
    meta_api_account_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    broker_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    broker_connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    trades: Mapped[list] = relationship("Trade", back_populates="user", lazy="noload")
