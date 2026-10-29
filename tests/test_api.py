import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_user(client, role="operator", email="op@example.com"):
    client.post("/auth/register", json={"email": email, "password": "password123", "role": role})
    r = client.post("/auth/login", data={"username": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_register_and_login(client):
    h = make_user(client)
    assert client.get("/vessels", headers=h).status_code == 200


def test_duplicate_email_rejected(client):
    make_user(client)
    r = client.post("/auth/register", json={"email": "op@example.com", "password": "password123"})
    assert r.status_code == 409


def test_wrong_password(client):
    make_user(client)
    r = client.post("/auth/login", data={"username": "op@example.com", "password": "nope-nope-1"})
    assert r.status_code == 401


def test_requires_token(client):
    assert client.get("/containers").status_code == 401


def test_viewer_cannot_write(client):
    h = make_user(client, role="viewer", email="v@example.com")
    r = client.post("/containers", json={"number": "MSKU1234567"}, headers=h)
    assert r.status_code == 403


def test_container_number_validation(client):
    h = make_user(client)
    r = client.post("/containers", json={"number": "BAD123"}, headers=h)
    assert r.status_code == 422


def test_full_lifecycle(client):
    h = make_user(client)
    v = client.post("/vessels", json={"name": "HMM Busan", "imo": "9876543"}, headers=h).json()
    c = client.post(
        "/containers", json={"number": "msku1234567", "size": "40", "vessel_id": v["id"]}, headers=h
    )
    assert c.status_code == 201 and c.json()["number"] == "MSKU1234567"

    for st, loc in [("gate_in", "Gate 2"), ("loaded", "Berth 5"), ("at_sea", "Pacific"), ("discharged", "LA")]:
        r = client.post(
            "/containers/MSKU1234567/events", json={"status": st, "location": loc}, headers=h
        )
        assert r.status_code == 201, r.text

    detail = client.get("/containers/MSKU1234567", headers=h).json()
    assert detail["status"] == "discharged"
    assert [e["status"] for e in detail["events"]] == [
        "booked", "gate_in", "loaded", "at_sea", "discharged"
    ]


def test_cannot_move_backwards(client):
    h = make_user(client)
    client.post("/containers", json={"number": "MSKU1234567"}, headers=h)
    client.post("/containers/MSKU1234567/events", json={"status": "gate_in", "location": "G1"}, headers=h)
    r = client.post("/containers/MSKU1234567/events", json={"status": "booked", "location": "x"}, headers=h)
    assert r.status_code == 409


def test_loading_needs_vessel(client):
    h = make_user(client)
    client.post("/containers", json={"number": "MSKU1234567"}, headers=h)
    r = client.post("/containers/MSKU1234567/events", json={"status": "loaded", "location": "B1"}, headers=h)
    assert r.status_code == 422


def test_list_filter_and_pagination(client):
    h = make_user(client)
    for i in range(5):
        client.post("/containers", json={"number": f"MSKU000000{i}"}, headers=h)
    client.post("/containers/MSKU0000001/events", json={"status": "gate_in", "location": "G1"}, headers=h)

    page = client.get("/containers?limit=2&offset=0", headers=h).json()
    assert page["total"] == 5 and len(page["items"]) == 2

    gate = client.get("/containers?status=gate_in", headers=h).json()
    assert gate["total"] == 1 and gate["items"][0]["number"] == "MSKU0000001"

    found = client.get("/containers?q=0003", headers=h).json()
    assert found["total"] == 1


def test_unknown_container_404(client):
    h = make_user(client)
    assert client.get("/containers/ZZZZ0000000", headers=h).status_code == 404


def test_root_redirects_to_docs(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/docs"
