from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class HealthEvent(Base):
    """A dated public-health event (data-model 1.7). Text is {"en","fr","ar"}."""

    __tablename__ = "health_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[dict] = mapped_column(JSONB)
    category: Mapped[str] = mapped_column(String)
    starts_on: Mapped[date] = mapped_column(Date, index=True)
    ends_on: Mapped[date] = mapped_column(Date)
    audience: Mapped[dict] = mapped_column(JSONB)  # {"roles": [...], "sex": "F"|"M"|None, "min_age", "max_age"}
    notify_days_before: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    organizer: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(String)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HealthEventPref(Base):
    """Opt-out per category: no row means the user follows it."""

    __tablename__ = "health_event_prefs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    category: Mapped[str] = mapped_column(String, primary_key=True)
    following: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
