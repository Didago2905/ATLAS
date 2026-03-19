import re
import os
from paddleocr import PaddleOCR

print("Inicializando PaddleOCR...")

ocr = PaddleOCR(lang="en")


# -----------------------------
# NORMALIZACIONES
# -----------------------------


def normalize_text(text):

    corrections = {"CERVEZADE": "CERVEZA DE", "OUE": "QUE", "O": "0"}

    for k, v in corrections.items():
        text = text.replace(k, v)

    return text


def normalize_name(text):

    text = text.upper()

    corrections = {
        "TIBURON": "TIBURÓN",
        "LEVIATAN": "LEVIATÁN",
    }

    for wrong, correct in corrections.items():
        text = text.replace(wrong, correct)

    return text.strip()


# -----------------------------
# EXTRAER TEXTO + POSICIONES
# -----------------------------


def extract_lines(image_path):

    result = ocr.ocr(image_path)

    lines = []

    for item in result[0]:

        box = item[0]
        text = item[1][0]
        conf = item[1][1]

        if conf < 0.80:
            continue

        y = box[0][1]

        lines.append({"text": text.strip(), "y": y})

    lines = sorted(lines, key=lambda x: x["y"])

    return lines


# -----------------------------
# EXTRAER DATOS TECNICOS
# -----------------------------


def extract_technical(lines):

    style = None
    abv = None
    color = None

    text = " ".join(lines)

    style_match = re.search(r"ESTILO[:\s]+([A-Z\s]+)", text)
    if style_match:
        style = style_match.group(1).title()

    abv_match = re.search(r"\d{1,2}(\.\d)?%", text)
    if abv_match:
        abv = abv_match.group()

    color_match = re.search(r"COLOR[:\s]+([A-Z\s]+)", text)
    if color_match:
        color = color_match.group(1).title()

    return style, abv, color


# -----------------------------
# EXTRAER PRECIOS
# -----------------------------


def extract_prices(lines):

    prices = {}

    text = " ".join(lines)

    text = text.replace("O", "0")

    patterns = {
        "taster": r"TASTER.*?\$(\d+)",
        "pinta_chica": r"PINTA CHICA.*?\$(\d+)",
        "pinta_grande": r"PINTA GRANDE.*?\$(\d+)",
        "jarra_chica": r"JARRA CHICA.*?\$(\d+)",
        "jarra_grande": r"JARRA GRANDE.*?\$(\d+)",
    }

    for key, pattern in patterns.items():

        m = re.search(pattern, text)

        if m:
            prices[key] = int(m.group(1))

    return prices


# -----------------------------
# PIPELINE PRINCIPAL
# -----------------------------


def extract_beer_data(image_path):

    print(f"\nProcesando: {image_path}")

    lines = extract_lines(image_path)

    if not lines:
        return None

    # dividir zonas usando posición Y
    y_values = [l["y"] for l in lines]

    top = min(y_values)
    bottom = max(y_values)

    height = bottom - top

    title_zone = top + height * 0.15
    tech_zone = top + height * 0.30
    price_zone = top + height * 0.75

    title_lines = []
    tech_lines = []
    desc_lines = []
    price_lines = []

    for line in lines:

        y = line["y"]
        text = normalize_text(line["text"])

        if y < title_zone:
            title_lines.append(text)

        elif y < tech_zone:
            tech_lines.append(text)

        elif y < price_zone:
            desc_lines.append(text)

        else:
            price_lines.append(text)

    # nombre
    name = None

    if title_lines:
        name = normalize_name(title_lines[0])

    # technical
    style, abv, color = extract_technical(tech_lines)

    # description
    description = " ".join(desc_lines)

    # prices
    prices = extract_prices(price_lines)

    return {
        "name": name,
        "style": style,
        "abv": abv,
        "color": color,
        "description": description,
        "prices": prices,
    }


# -----------------------------
# TEST EN LOTE
# -----------------------------


def batch_test(folder):

    for file in os.listdir(folder):

        if not file.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        path = os.path.join(folder, file)

        print("\n===================================")
        print("Procesando:", file)
        print("===================================")

        data = extract_beer_data(path)

        print("\nRESULTADO:")
        print(data)


if __name__ == "__main__":

    folder = os.path.join(os.path.dirname(__file__), "test_batch")

    batch_test(folder)
