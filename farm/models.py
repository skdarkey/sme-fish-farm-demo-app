from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Pond(Base):
    __tablename__ = "ponds"
    __table_args__ = (CheckConstraint("area_m2 > 0 AND depth_m > 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    area_m2: Mapped[float] = mapped_column(Float)
    depth_m: Mapped[float] = mapped_column(Float)


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (CheckConstraint("stocked_count > 0 AND initial_weight_g > 0"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pond_id: Mapped[int] = mapped_column(ForeignKey("ponds.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    species: Mapped[str] = mapped_column(String(100))
    stocked_on: Mapped[date] = mapped_column(Date)
    stocked_count: Mapped[int] = mapped_column(Integer)
    initial_weight_g: Mapped[float] = mapped_column(Float)


class DailyLog(Base):
    __tablename__ = "daily_logs"
    __table_args__ = (
        UniqueConstraint("batch_id", "day"),
        CheckConstraint("feed_kg >= 0 AND deaths >= 0 AND harvest_count >= 0 AND harvest_kg >= 0"),
        CheckConstraint("(harvest_count = 0 AND harvest_kg = 0) OR (harvest_count > 0 AND harvest_kg > 0)"),
        CheckConstraint("weight_g IS NULL OR weight_g > 0"),
        CheckConstraint("oxygen IS NULL OR oxygen >= 0"),
        CheckConstraint("ph IS NULL OR (ph >= 0 AND ph <= 14)"),
        CheckConstraint("temperature IS NULL OR (temperature >= 0 AND temperature <= 50)"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    feed_kg: Mapped[float] = mapped_column(Float, default=0)
    deaths: Mapped[int] = mapped_column(Integer, default=0)
    harvest_count: Mapped[int] = mapped_column(Integer, default=0)
    harvest_kg: Mapped[float] = mapped_column(Float, default=0)
    weight_g: Mapped[float | None] = mapped_column(Float)
    oxygen: Mapped[float | None] = mapped_column(Float)
    ph: Mapped[float | None] = mapped_column(Float)
    temperature: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(String(1000), default="")


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("issuer", "subject"),
                      CheckConstraint("role IN ('pending', 'stocktaker', 'manager')"))
    id: Mapped[int] = mapped_column(primary_key=True)
    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), default="")
    name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="pending")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AccessAudit(Base):
    __tablename__ = "access_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))
    target_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"))
    change: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ResearchDataset(Base):
    __tablename__ = "research_datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    release: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(Text)
    manifest: Mapped[dict] = mapped_column(JSON)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ResearchRecord(Base):
    """Versioned source rows; no inferred batch identity or invented inventory."""
    __tablename__ = "research_records"
    __table_args__ = (UniqueConstraint("dataset_id", "file", "row_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("research_datasets.id"), index=True)
    file: Mapped[str] = mapped_column(String(50))
    row_number: Mapped[int] = mapped_column(Integer)
    external_pond_id: Mapped[str] = mapped_column(String(100), index=True)
    region: Mapped[str] = mapped_column(String(100))
    observed_on: Mapped[date] = mapped_column(Date, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class WaterVisit(Base):
    __tablename__ = "water_visits"
    __table_args__ = (
        UniqueConstraint("pond_id", "day", "time"),
        CheckConstraint("ph IS NULL OR (ph >= 0 AND ph <= 14)"),
        CheckConstraint("oxygen IS NULL OR oxygen >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    pond_id: Mapped[int] = mapped_column(ForeignKey("ponds.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[str] = mapped_column(String(5))
    period: Mapped[str] = mapped_column(String(20))
    oxygen: Mapped[float | None] = mapped_column(Float)
    ph: Mapped[float | None] = mapped_column(Float)
    temperature: Mapped[float | None] = mapped_column(Float)
    secchi_cm: Mapped[float | None] = mapped_column(Float)
    tan_n: Mapped[float | None] = mapped_column(Float)
    tan_nh3: Mapped[float | None] = mapped_column(Float)
    nh3: Mapped[float | None] = mapped_column(Float)
    tds_ppt: Mapped[float | None] = mapped_column(Float)
    alkalinity: Mapped[float | None] = mapped_column(Float)
    hardness: Mapped[float | None] = mapped_column(Float)
    equipment: Mapped[str] = mapped_column(String(500), default="")
    observer: Mapped[str] = mapped_column(String(255))
    follow_up: Mapped[bool] = mapped_column(Boolean, default=False)
    actions_requested: Mapped[str] = mapped_column(Text, default="")
    actions_implemented: Mapped[str] = mapped_column(String(50), default="Not recorded")
    follow_up_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
