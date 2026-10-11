"""Backend → n8n event emitter (n8n-webhooks.md → Transport). Fire-and-forget: a daemon thread posts the
envelope with a 3 s timeout and logs failures, so the API never fails because n8n is down.

Callers use `n8n.emit(...)` through the module (not `from … import emit`) so tests can capture events.
"""

import logging
import threading
from datetime import UTC, datetime

import httpx
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from app.config import get_settings

log = logging.getLogger("medora.n8n")


def _post(event: str, data: dict) -> None:
    s = get_settings()
    try:
        httpx.post(s.n8n_webhook_url, timeout=3.0, headers={"X-Ward-Secret": s.n8n_event_secret},
                   json={"event": event, "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "data": data})
    except Exception as e:  # never break the API because n8n is down
        log.warning("n8n emit %s failed: %s", event, e)


def emit(event: str, data: dict) -> None:
    threading.Thread(target=_post, args=(event, data), daemon=True).start()


_PENDING = "n8n_pending"


def emit_after_commit(db, event: str, data: dict) -> None:
    """Queue an event on the session; it is emitted only if that session's transaction commits, so n8n
    never hears about an alert or dose that was rolled back."""
    db.info.setdefault(_PENDING, []).append((event, data))


@sa_event.listens_for(Session, "after_commit")
def _flush_pending(session) -> None:
    for event, data in session.info.pop(_PENDING, []):
        emit(event, data)


@sa_event.listens_for(Session, "after_soft_rollback")
def _drop_pending(session, previous_transaction) -> None:
    session.info.pop(_PENDING, None)
