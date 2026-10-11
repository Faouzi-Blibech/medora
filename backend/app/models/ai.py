from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AiSummary(Base):
    __tablename__ = "ai_summaries"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    ai_suggested: Mapped[dict] = mapped_column(JSONB)  # {summary, interactions, source}
    human_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotebookEntry(Base):
    __tablename__ = "notebook_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(Text)
    ai_suggested: Mapped[dict] = mapped_column(JSONB)  # {answer, citations, source}
    human_confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatConversation(Base):
    """A staff member's AI assistant conversation (doctor or nurse). Each message may be about one patient."""
    __tablename__ = "chat_conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String)  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"))
    meta: Mapped[dict | None] = mapped_column(JSONB)  # assistant: {citations, source, unverified}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Handover(Base):
    """A nurse shift handover (SBAR) the outgoing nurse confirmed: the draft as shown, and who confirmed it."""
    __tablename__ = "handovers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    ward: Mapped[str | None] = mapped_column(String)
    window_hours: Mapped[int] = mapped_column(Integer)
    ai_suggested: Mapped[dict] = mapped_column(JSONB)  # the SBAR draft incl. narrative and source (rules | llm)
    human_confirmed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
