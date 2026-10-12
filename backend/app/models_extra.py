from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from .models_tickets import Base, now_naive

class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True); value: Mapped[str] = mapped_column(String(200))

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True); stored_name: Mapped[str] = mapped_column(String(64), unique=True)
    mime: Mapped[str] = mapped_column(String(20)); width: Mapped[int]; height: Mapped[int]; created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive)

class BookingCodeJob(Base):
    __tablename__ = "booking_code_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    bookmaker: Mapped[str] = mapped_column(String(40)); status: Mapped[str] = mapped_column(String(12)); reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    per_selection: Mapped[dict] = mapped_column(JSON, default=dict); code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    confirmation_id: Mapped[str | None] = mapped_column(String(60), nullable=True); created_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive)

class PredictionEvaluation(Base):
    __tablename__ = "prediction_evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), unique=True)
    outcome: Mapped[int]; log_loss: Mapped[float]; brier: Mapped[float]; rps: Mapped[float]; evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=now_naive)
