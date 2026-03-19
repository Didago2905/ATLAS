import re
import os
from paddleocr import PaddleOCR


# --------------------------------
# INICIALIZAR OCR
# --------------------------------

print("Inicializando PaddleOCR...")

ocr = PaddleOCR(lang="en")


# --------------------------------
# NORMALIZAR NOMBRE
# --------------------------------


def normalize_name(text):

    text = text.upper()

    corrections = {
        "TIBURON": "TIBURÓN",
        "LEVIATAN": "LEVIATÁN",
    }

    for wrong, correct in corrections.items():
        text = text.replace(wrong, correct)

    return text.strip()


# --------------------------------
# EXTRAER DATOS TECNICOS
# --------------------------------


def extract_technical(line):

    style = None
    abv = None
    color = None

    style_match = re.search(r"ESTILO[:\s]+([A-Z\s]+)", line)
    if style_match:
        style = style_match.group(1).title()

    abv_match = re.search(r"\d{1,2}(\.\d)?%", line)
    if abv_match:
        abv = abv_match.group()

    color_match = re.search(r"COLOR[:\s]+([A-Z\s]+)", line)
    if color_match:
        color = color_match.group(1).title()

    return style, abv, color


# --------------------------------
# EXTRAER PRECIOS
# --------------------------------


def extract_prices(lines):

    prices = {}

    price_patterns = {
        "taster": r"TASTER.*?\$(\d+)",
        "pinta_chica": r"PINTA CHICA.*?\$(\d+)",
        "pinta_grande": r"PINTA GRANDE.*?\$(\d+)",
        "jarra_chica": r"JARRA CHICA.*?\$(\d+)",
        "jarra_grande": r"JARRA GRANDE.*?\$(\d+)",
    }

    text = " ".join(lines)

    # correcciones OCR comunes
    text = text.replace("O", "0")
    text = text.replace("I", "1")

    for key, pattern in price_patterns.items():

        match = re.search(pattern, text)

        if match:
            prices[key] = int(match.group(1))

    return prices


# --------------------------------
# EXTRAER DESCRIPCION
# --------------------------------


def extract_description(lines):

    desc_lines = []

    for line in lines:

        if "$" in line:
            continue

        if "ESTILO" in line:
            continue

        if len(line) < 10:
            continue

        desc_lines.append(line)

    text = " ".join(desc_lines)

    # correcciones OCR
    text = text.replace("CERVEZADE", "CERVEZA DE")

    return text


# --------------------------------
# EXTRAER TEXTO CON OCR
# --------------------------------


def extract_text(image_path):

    results = ocr.ocr(image_path)

    lines = []

    for line in results[0]:

        text = line[1][0]
        conf = line[1][1]

        if conf < 0.80:
            continue

        text = text.strip()

        if len(text) < 2:
            continue

        lines.append(text)

    return lines


# --------------------------------
# PIPELINE PRINCIPAL
# --------------------------------


def extract_beer_data(image_path):

    print(f"\nProcesando: {image_path}")

    lines = extract_text(image_path)

    if not lines:
        return None

    # -----------------------------
    # DETECTAR NOMBRE
    # -----------------------------

    name = None


    for line in lines:

     if "ESTILO" in line:
        break

     if ":" in line:
        continue

     if "%" in line:
        continue

     if "$" in line:
        continue

     if len(line) < 3:
        continue

    name = normalize_name(line)

    # -----------------------------

    style = None
    abv = None
    color = None

    description_lines = []
    price_lines = []

    for line in lines:

        if "ESTILO" in line:

            style, abv, color = extract_technical(line)

        elif "$" in line:

            price_lines.append(line)

        else:

            description_lines.append(line)

    description = extract_description(description_lines)

    prices = extract_prices(price_lines)

    return {
        "name": name,
        "style": style,
        "abv": abv,
        "color": color,
        "description": description,
        "prices": prices,
    }


# --------------------------------
# TEST EN LOTE
# --------------------------------


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


# --------------------------------

if __name__ == "__main__":

    folder = os.path.join(os.path.dirname(__file__), "test_batch")

    batch_test(folder)
