from fastapi import APIRouter, Request
from pydantic import BaseModel
from datetime import datetime
import json
from pathlib import Path

from app.audit.stats import get_audit_stats

router = APIRouter(prefix="/audit", tags=["audit"])

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "audit/logs/audit_log.jsonl"

print("AUDIT FILE:", LOG_FILE.resolve())


class AuditEvent(BaseModel):
    event: str
    beer_id: int | None = None
    metadata: dict | None = None


@router.post("/")
def create_audit_event(payload: AuditEvent, request: Request):

    print("\n🔥 AUDIT EVENT")
    print("time:", datetime.utcnow())
    print("event:", payload.event)
    print("beer_id:", payload.beer_id)
    print("metadata:", payload.metadata)

    log_entry = {
        "time": datetime.utcnow().isoformat(),
        "event": payload.event,
        "beer_id": payload.beer_id,
        "metadata": payload.metadata,
        "ip": request.client.host,
    }

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    return {"success": True, "received": payload.dict()}


@router.get("/stats")
def read_audit_stats():

    return get_audit_stats()
