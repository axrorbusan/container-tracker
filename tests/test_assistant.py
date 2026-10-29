import pytest

from tests.test_api import client, make_user  # noqa: F401  (fixtures)


@pytest.fixture()
def seeded(client):
    h = make_user(client)
    v = client.post("/vessels", json={"name": "HMM Busan", "imo": "9876543"}, headers=h).json()
    client.post("/containers", json={"number": "MSKU1234567", "vessel_id": v["id"]}, headers=h)
    client.post("/containers", json={"number": "TEMU7654321"}, headers=h)
    client.post("/containers", json={"number": "CMAU1111111", "vessel_id": v["id"]}, headers=h)
    for st, loc, note in [("gate_in", "Gate 2", "customs cleared"), ("loaded", "Berth 5", None), ("at_sea", "Pacific", None)]:
        client.post("/containers/MSKU1234567/events", json={"status": st, "location": loc, "note": note}, headers=h)
    client.post("/containers/CMAU1111111/events", json={"status": "gate_in", "location": "Gate 1", "note": "damaged seal"}, headers=h)
    return client, h


# Mini eval set: (question, tool that should answer, text that must appear)
EVAL = [
    ("Where is MSKU1234567 now?", "container_history", "at_sea"),
    ("history of msku1234567", "container_history", "Berth 5"),
    ("Which containers are at sea?", "list_by_status", "MSKU1234567"),
    ("show containers that are booked", "list_by_status", "TEMU7654321"),
    ("How many containers do we have?", "count_by_status", "3 containers"),
    ("which one had a damaged seal", "search_events", "CMAU1111111"),
    ("customs cleared", "search_events", "MSKU1234567"),
]


@pytest.mark.parametrize("question,tool,expected", EVAL)
def test_eval_questions(seeded, question, tool, expected):
    client, h = seeded
    r = client.post("/ask", json={"question": question}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool"] == tool
    assert expected in body["answer"]


def test_unknown_container(seeded):
    client, h = seeded
    r = client.post("/ask", json={"question": "where is ZZZZ0000000"}, headers=h)
    assert "could not find" in r.json()["answer"]


def test_ask_requires_login(client):
    assert client.post("/ask", json={"question": "hello there"}).status_code == 401
