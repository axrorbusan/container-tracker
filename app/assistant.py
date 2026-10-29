"""Ask questions about containers in plain language.

Flow: question -> router picks a tool -> tool reads the database -> answer.
Free-text questions go through a small BM25 retriever over event history.
If ANTHROPIC_API_KEY is set, an LLM rewrites the facts into a nicer answer;
without a key the answer is built directly from the retrieved facts, so the
app and the tests work offline.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .schemas import STATUSES

CONTAINER_IN_TEXT = re.compile(r"\b([A-Za-z]{4}\d{7})\b")


@dataclass
class Answer:
    answer: str
    tool: str
    sources: list[str]


# ---------- retrieval (BM25 over event history) ----------
def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def event_documents(db: Session) -> list[tuple[str, str]]:
    """One short document per event: (source_id, text)."""
    rows = db.execute(
        select(models.Container.number, models.ContainerEvent)
        .join(models.ContainerEvent, models.ContainerEvent.container_id == models.Container.id)
    ).all()
    docs = []
    for number, e in rows:
        text = f"{number} {e.status} at {e.location}. {e.note or ''} {e.occurred_at:%Y-%m-%d}"
        docs.append((f"{number}#{e.id}", text))
    return docs


def bm25_search(query: str, docs: list[tuple[str, str]], k: int = 5, k1=1.5, b=0.75):
    if not docs:
        return []
    toks = [_tokens(t) for _, t in docs]
    avg = sum(map(len, toks)) / len(toks) or 1
    df = Counter(w for t in toks for w in set(t))
    n = len(docs)
    q = _tokens(query)
    scored = []
    for (sid, text), t in zip(docs, toks):
        tf = Counter(t)
        score = 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            score += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        if score > 0:
            scored.append((score, sid, text))
    scored.sort(reverse=True)
    return [(sid, text) for _, sid, text in scored[:k]]


# ---------- tools ----------
def tool_container_history(db: Session, number: str) -> Answer:
    c = db.scalar(select(models.Container).where(models.Container.number == number.upper()))
    if c is None:
        return Answer(f"I could not find container {number.upper()}.", "container_history", [])
    steps = " -> ".join(f"{e.status} ({e.location})" for e in c.events)
    vessel = c.vessel.name if c.vessel else "no vessel yet"
    nxt = STATUSES[STATUSES.index(c.status) + 1:]
    tail = f" Next step: {nxt[0]}." if nxt else " It has finished its journey."
    return Answer(
        f"{c.number} is {c.status} on {vessel}. History: {steps}.{tail}",
        "container_history",
        [f"{c.number}#{e.id}" for e in c.events],
    )


def tool_count_by_status(db: Session) -> Answer:
    rows = dict(db.execute(select(models.Container.status, func.count()).group_by(models.Container.status)).all())
    if not rows:
        return Answer("There are no containers yet.", "count_by_status", [])
    parts = [f"{s}: {rows[s]}" for s in STATUSES if s in rows]
    return Answer(f"{sum(rows.values())} containers in total. " + ", ".join(parts) + ".", "count_by_status", [])


def tool_list_status(db: Session, status: str) -> Answer:
    nums = db.scalars(select(models.Container.number).where(models.Container.status == status).order_by(models.Container.number)).all()
    if not nums:
        return Answer(f"No containers are {status} right now.", "list_by_status", [])
    return Answer(f"{len(nums)} container(s) {status}: {', '.join(nums)}.", "list_by_status", list(nums))


def tool_search(db: Session, question: str) -> Answer:
    hits = bm25_search(question, event_documents(db))
    if not hits:
        return Answer("I found nothing in the event history that matches that.", "search_events", [])
    return Answer("Closest events: " + " | ".join(t for _, t in hits), "search_events", [s for s, _ in hits])


# ---------- router ----------
_STATUS_WORDS = {
    "booked": "booked", "gate in": "gate_in", "gate-in": "gate_in", "gate_in": "gate_in",
    "loaded": "loaded", "at sea": "at_sea", "at_sea": "at_sea", "sailing": "at_sea",
    "discharged": "discharged", "gate out": "gate_out", "gate-out": "gate_out", "gate_out": "gate_out",
}


def route(question: str, db: Session) -> Answer:
    q = question.lower()
    m = CONTAINER_IN_TEXT.search(question)
    if m:
        return tool_container_history(db, m.group(1))
    status = next((v for k, v in _STATUS_WORDS.items() if k in q), None)
    if status and any(w in q for w in ("which", "list", "show", "what")):
        return tool_list_status(db, status)
    if any(w in q for w in ("how many", "count", "total", "summary")):
        return tool_count_by_status(db)
    return tool_search(db, question)


def _polish_with_llm(question: str, facts: str) -> str | None:
    if not settings.anthropic_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": settings.llm_model,
                "max_tokens": 300,
                "system": "Answer the question using ONLY the facts given. If they are not enough, say so. Be short.",
                "messages": [{"role": "user", "content": f"Facts: {facts}\n\nQuestion: {question}"}],
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    except Exception:
        return None  # fall back to the plain answer


def ask(db: Session, question: str) -> Answer:
    result = route(question, db)
    polished = _polish_with_llm(question, result.answer)
    if polished:
        result.answer = polished
    return result
