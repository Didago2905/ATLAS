import json
from collections import Counter
from pathlib import Path

from app.core.database import SessionLocal
from app.models.beer import Beer

LOG_FILE = Path("app/audit/logs/audit_log.jsonl")


def get_audit_stats():

    if not LOG_FILE.exists():
        return {
            "total_events": 0,
            "unique_devices": 0,
            "beer_opens": [],
            "top_beer": None,
        }

    beer_counter = Counter()
    unique_devices = set()
    total_events = 0

    db = SessionLocal()

    with open(LOG_FILE, "r", encoding="utf-8") as f:

        for line in f:

            try:
                event = json.loads(line)

                if event.get("event") == "open_beer":

                    beer_id = event.get("beer_id")

                    ip = event.get("ip")

                    if ip:
                        unique_devices.add(ip)

                    if beer_id is not None:
                        beer_counter[beer_id] += 1

                    total_events += 1

            except Exception:
                continue

    top_beer = None

    if beer_counter:

        beer_id, opens = beer_counter.most_common(1)[0]

        beer = db.query(Beer).filter(Beer.id == beer_id).first()

        top_beer = {
            "beer_id": beer_id,
            "beer_name": beer.name if beer else "Unknown",
            "opens": opens,
        }

    beer_opens = []

    for beer_id, opens in beer_counter.items():

        beer = db.query(Beer).filter(Beer.id == beer_id).first()

        beer_opens.append(
            {
                "beer_id": beer_id,
                "beer_name": beer.name if beer else "Unknown",
                "opens": opens,
            }
        )

    return {
    "total_events": total_events,

    "unique_devices": len(unique_devices),

    "top_beer": top_beer,

    "top_beers": sorted(
        beer_opens,
        key=lambda x: x["opens"],
        reverse=True
    )[:5],
}