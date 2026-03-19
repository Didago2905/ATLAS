import os
from layout_detector import detect_layout, split_layout

folder = "atlas_vision/test_batch"

for file in os.listdir(folder):

    if not file.lower().endswith(("jpg", "png")):
        continue

    path = os.path.join(folder, file)

    print("\n========================")
    print(file)
    print("========================")

    lines = detect_layout(path)

    title, tech, desc, prices = split_layout(lines)

    print("\nTITLE:")
    print(title)

    print("\nTECH:")
    print(tech)

    print("\nDESC:")
    print(desc[:2])

    print("\nPRICES:")
    print(prices)
