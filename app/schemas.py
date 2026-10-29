import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Container lifecycle, in order. An event may only move forward.
STATUSES = ["booked", "gate_in", "loaded", "at_sea", "discharged", "gate_out"]
CONTAINER_RE = re.compile(r"^[A-Z]{4}\d{7}$")


class UserCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=72)
    role: str = Field(default="viewer", pattern="^(viewer|operator)$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VesselCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    imo: str = Field(pattern=r"^\d{7}$")


class VesselOut(VesselCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ContainerCreate(BaseModel):
    number: str
    size: str = Field(default="40", pattern="^(20|40)$")
    vessel_id: int | None = None

    @field_validator("number")
    @classmethod
    def check_number(cls, v: str) -> str:
        v = v.upper()
        if not CONTAINER_RE.match(v):
            raise ValueError("container number must be 4 letters + 7 digits, e.g. MSKU1234567")
        return v


class EventCreate(BaseModel):
    status: str
    location: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("status")
    @classmethod
    def check_status(cls, v: str) -> str:
        if v not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        return v


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    location: str
    note: str | None
    occurred_at: datetime


class ContainerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    number: str
    size: str
    status: str
    vessel_id: int | None


class ContainerDetail(ContainerOut):
    events: list[EventOut]


class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ContainerOut]
