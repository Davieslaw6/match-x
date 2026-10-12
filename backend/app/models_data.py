from datetime import datetime
from decimal import Decimal
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Competition(Base):
    __tablename__ = "competitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(default=True)

class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    norm: Mapped[str] = mapped_column(String(100), unique=True)
    favourite: Mapped[bool] = mapped_column(default=False)

class TeamAlias(Base):
    __tablename__ = "team_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    alias_norm: Mapped[str] = mapped_column(String(100), unique=True)

class Fixture(Base):
    __tablename__ = "fixtures"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    provider_fixture_id: Mapped[str] = mapped_column(String(50))
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    season: Mapped[str] = mapped_column(String(9))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime)  # naive UTC by convention
    status: Mapped[str] = mapped_column(String(20))
    __table_args__ = (UniqueConstraint("provider", "provider_fixture_id"),
                      Index("ix_fixture_dedup", "competition_id", "season", "home_team_id", "away_team_id", "kickoff_utc"),
                      Index("ix_fixture_kickoff", "kickoff_utc"))

class MatchResult(Base):
    __tablename__ = "match_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"), unique=True)
    home_goals: Mapped[int] = mapped_column()
    away_goals: Mapped[int] = mapped_column()

class MarketOdds(Base):  # append-only: callers only ever insert
    __tablename__ = "market_odds"
    id: Mapped[int] = mapped_column(primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"), index=True)
    bookmaker: Mapped[str] = mapped_column(String(40)); market: Mapped[str] = mapped_column(String(20))
    selection: Mapped[str] = mapped_column(String(20)); line: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    observed_at: Mapped[datetime] = mapped_column(DateTime); provider: Mapped[str] = mapped_column(String(30))
    is_closing: Mapped[bool] = mapped_column(default=False)

class ProviderRawPayload(Base):
    __tablename__ = "provider_raw_payloads"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30)); content_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON); fetched_at: Mapped[datetime] = mapped_column(DateTime)

class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(40)); started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(15))
    inserted: Mapped[int] = mapped_column(default=0); updated: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0); failed: Mapped[int] = mapped_column(default=0)
    error_summary: Mapped[str | None] = mapped_column(String(500))
