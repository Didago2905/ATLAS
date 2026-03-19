from paddleocr import PaddleOCR

ocr = PaddleOCR(lang="en")


def detect_layout(image_path):

    result = ocr.ocr(image_path)

    lines = []

    for item in result[0]:

        box = item[0]
        text = item[1][0]
        conf = item[1][1]

        if conf < 0.80:
            continue

        y = box[0][1]

        lines.append({"text": text, "y": y})

    lines = sorted(lines, key=lambda x: x["y"])

    return lines


def split_layout(lines):

    title = []
    technical = []
    description = []
    prices = []

    for l in lines:

        text = l["text"].upper()

        # FILTRO BASURA OCR (logos)
        if text in ["IBURON", "IBUROI", "BURO", "BUR", "ON"]:
            continue

        # PRECIOS
        if "$" in text:
            prices.append(text)
            continue

        # LINEA TECNICA
        if "ESTILO" in text or "%" in text:
            technical.append(text)
            continue

        # TITULO
        if not title and len(text) > 3:
            title.append(text)
            continue

        # DESCRIPCION
        description.append(text)

    return title, technical, description, prices
