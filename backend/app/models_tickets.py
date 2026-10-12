from datetime import datetime
from decimal import Decimal
from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow
def now_naive(): return utcnow().replace(tzinfo=None)

class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100)); status: Mapped[str] = mapped_column(String(10), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive)

class TicketSelection(Base):
    __tablename__ = "ticket_selections"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    fixture_id: Mapped[int | None] = mapped_column(ForeignKey("fixtures.id"), nullable=True)
    fixture_label: Mapped[str] = mapped_column(String(200)); market: Mapped[str] = mapped_column(String(20)); outcome: Mapped[str] = mapped_column(String(40))
    odds: Mapped[Decimal] = mapped_column(Numeric(10, 3))  # snapshot at selection time
    bookmaker: Mapped[str | None] = mapped_column(String(40), nullable=True)

class TicketRevision(Base):
    __tablename__ = "ticket_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    before: Mapped[list] = mapped_column(JSON); after: Mapped[list | dict] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(20)); note: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive)

class PendingChange(Base):
    __tablename__ = "pending_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True); kind: Mapped[str] = mapped_column(String(12))
    ticket_id: Mapped[int | None] = mapped_column(nullable=True, index=True); payload: Mapped[dict] = mapped_column(JSON)
    base_hash: Mapped[str] = mapped_column(String(64)); expires_at: Mapped[datetime] = mapped_column(DateTime)

class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80)); route: Mapped[str] = mapped_column(String(120)); body_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON); created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive)
    __table_args__ = (UniqueConstraint("key", "route"),)
