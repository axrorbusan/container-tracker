from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # viewer | operator


class Vessel(Base):
    __tablename__ = "vessels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    imo: Mapped[str] = mapped_column(String(7), unique=True)

    containers: Mapped[list["Container"]] = relationship(back_populates="vessel")


class Container(Base):
    __tablename__ = "containers"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(11), unique=True, index=True)  # e.g. MSKU1234567
    size: Mapped[str] = mapped_column(String(4), default="40")  # 20 | 40
    status: Mapped[str] = mapped_column(String(20), default="booked", index=True)
    vessel_id: Mapped[int | None] = mapped_column(ForeignKey("vessels.id"), nullable=True)

    vessel: Mapped[Vessel | None] = relationship(back_populates="containers")
    events: Mapped[list["ContainerEvent"]] = relationship(
        back_populates="container", order_by="ContainerEvent.occurred_at", cascade="all, delete-orphan"
    )


class ContainerEvent(Base):
    __tablename__ = "container_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[int] = mapped_column(ForeignKey("containers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    location: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    container: Mapped[Container] = relationship(back_populates="events")
