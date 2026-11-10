import json
import atexit
import re
import subprocess
from pathlib import Path

from devtools.qr.generate_qr import generate_qr
from devtools.telegram.bot import send_message, send_photo
from app.core.bot_observability import event

event("notifications", "started")
atexit.register(event, "notifications", "stopped")

URL_PATTERN = re.compile(r"https://[^\s]+\.trycloudflare\.com")
RUNTIME_FILE = Path("devtools/runtime/current_tunnel.json")

print("=" * 50)
print("ATLAS Dev Launcher")
print("=" * 50)
print()

print("Iniciando Cloudflare...\n")

process = subprocess.Popen(
    [
        "cloudflared",
        "tunnel",
        "--url",
        "http://localhost:5173",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

url_found = False

for line in process.stdout:
    print(line, end="")

    if url_found:
        continue

    match = URL_PATTERN.search(line)

    if not match:
        continue

    url = match.group()

    public_url = url
    admin_url = f"{url}/admin"

    runtime = {
        "provider": "cloudflare",
        "status": "connected",
        "url": public_url,
    }

    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(runtime, f, indent=4, ensure_ascii=False)

    # Generar QR del catálogo público
    generate_qr()

    print("\nEnviando notificación a Telegram...")

    # Enviar mensaje
    send_message(
        "🦈 ATLAS ONLINE\n\n"
        f"🌍 Catálogo Público\n"
        f"{public_url}\n\n"
        f"⚙️ Panel de Administración\n"
        f"{admin_url}\n\n"
        "────────────────────\n\n"
        "Estado de Servicios\n\n"
        "🟢 Backend\n"
        "🟢 Frontend\n"
        "🟢 Cloudflare\n\n"
        "📱 El QR adjunto abre el catálogo público."
    )

    # Enviar QR del catálogo público
    send_photo(
        "devtools/qr/atlas_qr.png",
        f"🍺 Catálogo Público de ATLAS\n\n{public_url}"
    )

    print("Telegram OK")

    print("\n" + "=" * 50)
    print("TÚNEL DETECTADO")
    print(public_url)
    print("Runtime guardado correctamente")
    print("=" * 50 + "\n")

    url_found = True

process.wait()
