from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .database import Base, engine, get_db
from .security import create_token, current_user, hash_password, require_operator, verify_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Container Tracker API",
    description="Track shipping containers through a terminal: gate-in, loading, sea, discharge, gate-out.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- auth ----------
@app.post("/auth/register", response_model=schemas.UserOut, status_code=201, tags=["auth"])
def register(body: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(models.User).where(models.User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = models.User(email=body.email, hashed_password=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.Token, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == form.username))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return schemas.Token(access_token=create_token(user))


# ---------- vessels ----------
@app.post("/vessels", response_model=schemas.VesselOut, status_code=201, tags=["vessels"])
def create_vessel(body: schemas.VesselCreate, db: Session = Depends(get_db), _=Depends(require_operator)):
    clash = db.scalar(
        select(models.Vessel).where((models.Vessel.name == body.name) | (models.Vessel.imo == body.imo))
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "Vessel name or IMO already exists")
    vessel = models.Vessel(**body.model_dump())
    db.add(vessel)
    db.commit()
    db.refresh(vessel)
    return vessel


@app.get("/vessels", response_model=list[schemas.VesselOut], tags=["vessels"])
def list_vessels(db: Session = Depends(get_db), _=Depends(current_user)):
    return db.scalars(select(models.Vessel).order_by(models.Vessel.name)).all()


# ---------- containers ----------
@app.post("/containers", response_model=schemas.ContainerOut, status_code=201, tags=["containers"])
def create_container(body: schemas.ContainerCreate, db: Session = Depends(get_db), _=Depends(require_operator)):
    if db.scalar(select(models.Container).where(models.Container.number == body.number)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Container number already exists")
    if body.vessel_id is not None and db.get(models.Vessel, body.vessel_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vessel not found")
    container = models.Container(**body.model_dump())
    container.events.append(models.ContainerEvent(status="booked", location="booking", note="created"))
    db.add(container)
    db.commit()
    db.refresh(container)
    return container


@app.get("/containers", response_model=schemas.Page, tags=["containers"])
def list_containers(
    status_filter: str | None = Query(default=None, alias="status"),
    vessel_id: int | None = None,
    q: str | None = Query(default=None, description="search in container number"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(current_user),
):
    stmt = select(models.Container)
    if status_filter:
        stmt = stmt.where(models.Container.status == status_filter)
    if vessel_id is not None:
        stmt = stmt.where(models.Container.vessel_id == vessel_id)
    if q:
        stmt = stmt.where(models.Container.number.contains(q.upper()))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(models.Container.id).limit(limit).offset(offset)).all()
    return schemas.Page(total=total, limit=limit, offset=offset, items=items)


@app.get("/containers/{number}", response_model=schemas.ContainerDetail, tags=["containers"])
def get_container(number: str, db: Session = Depends(get_db), _=Depends(current_user)):
    container = db.scalar(
        select(models.Container)
        .where(models.Container.number == number.upper())
        .options(selectinload(models.Container.events))
    )
    if container is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container not found")
    return container


@app.post("/containers/{number}/events", response_model=schemas.EventOut, status_code=201, tags=["containers"])
def add_event(number: str, body: schemas.EventCreate, db: Session = Depends(get_db), _=Depends(require_operator)):
    container = db.scalar(select(models.Container).where(models.Container.number == number.upper()))
    if container is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Container not found")
    # An event may only move the container forward in its lifecycle.
    if schemas.STATUSES.index(body.status) <= schemas.STATUSES.index(container.status):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot go from '{container.status}' to '{body.status}'. Next allowed: "
            f"{schemas.STATUSES[schemas.STATUSES.index(container.status) + 1:] or 'none (final)'}",
        )
    if body.status in ("loaded", "at_sea") and container.vessel_id is None:
        raise HTTPException(422, "Assign a vessel before loading")
    event = models.ContainerEvent(container_id=container.id, **body.model_dump())
    container.status = body.status
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
