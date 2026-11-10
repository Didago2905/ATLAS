import json
from pathlib import Path

import requests
from app.core.bot_observability import event

CONFIG_FILE = Path("devtools/config.json")

with open(CONFIG_FILE, encoding="utf-8") as f:
    config = json.load(f)

BOT_TOKEN = config["telegram"]["bot_token"]
CHAT_ID = config["telegram"]["chat_id"]

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(text: str):

    try:
        response = requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
        response.raise_for_status()
    except Exception:
        event("notifications", "operation_failed")
        raise
    event("notifications", "operation_ok")

    print("Telegram mensaje OK")


def send_photo(photo_path: str, caption: str | None = None):

    try:
        with open(photo_path, "rb") as photo:
            response = requests.post(
                f"{BASE_URL}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": caption or ""},
                files={"photo": photo},
                timeout=30,
            )
        response.raise_for_status()
    except Exception:
        event("notifications", "operation_failed")
        raise
    event("notifications", "operation_ok")

    print("Telegram foto OK")


if __name__ == "__main__":

    send_message("🦈 ATLAS\n\nLa integración funciona correctamente.")

    send_photo(
        "devtools/qr/atlas_qr.png",
        "QR de prueba"
    )
