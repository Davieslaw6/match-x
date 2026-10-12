from datetime import datetime
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, event
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow

class Prediction(Base):
    """Immutable. A new run inserts a new row that supersedes the old one."""
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # live | backtest
    model_version: Mapped[str] = mapped_column(String(40))
    data_cutoff_at: Mapped[datetime] = mapped_column(DateTime)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime)  # snapshot, lets the DB enforce the timing rule
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: utcnow().replace(tzinfo=None))
    probabilities: Mapped[dict] = mapped_column(JSON)
    features: Mapped[dict] = mapped_column(JSON)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"), nullable=True, unique=True)
    __table_args__ = (CheckConstraint("kind IN ('live','backtest')", name="ck_pred_kind"),
        CheckConstraint("kind = 'backtest' OR (data_cutoff_at < kickoff_utc AND created_at < kickoff_utc)", name="ck_pred_before_kickoff"))

@event.listens_for(Prediction, "before_update")
def _no_update(mapper, conn, target): raise ValueError("predictions are immutable; insert a superseding row")
@event.listens_for(Prediction, "before_delete")
def _no_delete(mapper, conn, target): raise ValueError("predictions are immutable")
