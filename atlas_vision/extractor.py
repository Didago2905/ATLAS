import os
import re
import cv2
import numpy as np
import easyocr
import pytesseract


# --------------------------------
# CONFIGURACIÓN TESSERACT
# --------------------------------

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR\tessdata"

reader = easyocr.Reader(["es"], gpu=False)


# --------------------------------
# PREPROCESADO
# --------------------------------

def preprocess_image(image_path):

    print("Cargando imagen...")

    image = cv2.imread(image_path)

    if image is None:
        print("❌ ERROR: No se pudo cargar la imagen.")
        return None

    print("Imagen cargada correctamente.")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)

    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(contrast, -1, kernel)

    return sharpened


# --------------------------------
# RECORTAR REGIONES
# --------------------------------

def crop_regions(image):

    h, w = image.shape

    title = image[int(h * 0.00): int(h * 0.18), :]
    technical = image[int(h * 0.18): int(h * 0.30), :]
    description = image[int(h * 0.30): int(h * 0.70), :]
    prices = image[int(h * 0.70): int(h * 1.00), :]

    return title, technical, description, prices


# --------------------------------
# EXTRAER NOMBRE
# --------------------------------

def extract_name(region):

    results = reader.readtext(region, detail=1)

    candidates = []

    for box, text, conf in results:
        height = abs(box[3][1] - box[0][1])
        candidates.append((text, height))

    if not candidates:
        return None

    name = max(candidates, key=lambda x: x[1])[0]

    return normalize_name(name)


# --------------------------------
# NORMALIZAR NOMBRE
# --------------------------------

def normalize_name(name):

    if not name:
        return None

    name = name.upper()

    corrections = {
        "TIRIRÁN": "TIBURÓN",
        "TIRIRÓN": "TIBURÓN",
        "TIBVRÓN": "TIBURÓN",
        "TIBURON": "TIBURÓN",
        "MAKI": "MAKO",
        "MAKD": "MAKO",
        "MAK0": "MAKO",
    }

    for wrong, correct in corrections.items():
        name = name.replace(wrong, correct)

    name = re.sub(r"[^A-ZÁÉÍÓÚÑ ]", "", name)

    return name.strip()


# --------------------------------
# EXTRAER LINEA TÉCNICA
# --------------------------------

def extract_technical(region):

    text = " ".join(reader.readtext(region, detail=0))

    style = None
    abv = None
    color = None

    style_match = re.search(r"Estilo[:\s]+([A-Za-z\s]+)", text, re.IGNORECASE)
    if style_match:
        style = style_match.group(1).title()

    abv_match = re.search(r"\d{1,2}(\.\d{1,2})?%", text)
    if abv_match:
        abv = abv_match.group()

        if int(abv.replace("%", "").split(".")[0]) > 20:
            abv = abv[0] + "." + abv[1:]

    color_match = re.search(
        r"Color[:\s]+([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+)", text, re.IGNORECASE
    )
    if color_match:
        color = color_match.group(1).capitalize()

    return style, abv, color


# --------------------------------
# NORMALIZAR DESCRIPCIÓN
# --------------------------------

def normalize_description(text):

    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^A-ZÁÉÍÓÚÑ]+", "", text)

    corrections = {
        "ABUNDAOTE": "ABUNDANTE",
        "COOTEQIDO": "CONTENIDO",
        "RMARGOR": "AMARGOR",
        "IDEOTE": "IDEAL",
        "UERSIÓO": "VERSIÓN",
        "CERUEZA": "CERVEZA",
        "UO": "UN",
        "TIEOE": "TIENE",
        "IFUSIÓN": "INFUSIÓN",
        "TIBURON": "TIBURÓN",
        "CARACTER": "CARÁCTER",
    }

    for wrong, correct in corrections.items():
        text = text.replace(wrong, correct)

    return text.strip().upper()


# --------------------------------
# EXTRAER DESCRIPCIÓN
# --------------------------------

def extract_description(region):

    text = pytesseract.image_to_string(region, lang="spa", config="--psm 6")

    return normalize_description(text)


# --------------------------------
# EXTRAER PRECIOS
# --------------------------------

def extract_prices(region):

    text = pytesseract.image_to_string(region, lang="spa", config="--psm 6")

    prices = {}

    matches = re.findall(
        r"(TASTER|PINTA CHICA|PINTA GRANDE|JARRA CHICA|JARRA GRANDE).*?\$(\d+)",
        text
    )

    for name, price in matches:
        key = name.lower().replace(" ", "_")
        prices[key] = int(price)

    return prices


# --------------------------------
# PIPELINE PRINCIPAL
# --------------------------------

def extract_beer_data(image_path):

    print(f"\nProcesando: {image_path}\n")

    image = preprocess_image(image_path)

    if image is None:
        return None

    title, technical, description, prices = crop_regions(image)

    name = extract_name(title)
    style, abv, color = extract_technical(technical)
    description = extract_description(description)
    prices = extract_prices(prices)

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