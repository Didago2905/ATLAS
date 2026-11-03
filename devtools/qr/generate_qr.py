import json
from pathlib import Path

import qrcode


RUNTIME = Path("devtools/runtime/current_tunnel.json")
OUTPUT = Path("devtools/qr/atlas_qr.png")


def generate_qr():

    with open(RUNTIME, encoding="utf-8") as f:
        runtime = json.load(f)

    url = runtime["url"]

    img = qrcode.make(url)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT)

    print("=" * 50)
    print("QR generado correctamente")
    print(url)
    print(OUTPUT)
    print("=" * 50)


if __name__ == "__main__":
    generate_qr()