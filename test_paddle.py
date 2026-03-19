from paddleocr import PaddleOCR

print("Inicializando OCR...")

ocr = PaddleOCR(lang="en")

image_path = (
    "atlas_vision/test_batch/Leviatan_Mesa de trabajo 1_Mesa de trabajo 1-01-01-01.jpg"
)

print("Procesando imagen...\n")

results = ocr.ocr(image_path)

for line in results[0]:
    text = line[1][0]
    confidence = line[1][1]

    print(f"{text} ({confidence:.2f})")
