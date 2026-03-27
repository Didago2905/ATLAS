import { useState } from "react";
import { parseBeerText } from "../utils/parseBeerText";

export default function ParserPage() {
    const [text, setText] = useState("");
    const [parsedBeer, setParsedBeer] = useState(null);

    const handleParse = () => {
        const result = parseBeerText(text);
        console.log("Parsed:", result);
        setParsedBeer(result);
    };

    return (
        <div className="p-6 grid grid-cols-2 gap-6">

            {/* 🔹 INPUT */}
            <div>
                <h2 className="text-xl font-bold mb-4">Parser ATLAS 🍺</h2>

                <textarea
                    className="w-full h-80 p-3 border rounded"
                    placeholder="Pega aquí la ficha de la cerveza..."
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                />

                <button
                    onClick={handleParse}
                    className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
                >
                    Parsear
                </button>
            </div>

            {/* 🔹 PREVIEW */}
            <div>
                <h2 className="text-xl font-bold mb-4">Preview</h2>

                {!parsedBeer ? (
                    <p className="text-gray-500">
                        Aquí aparecerá la cerveza parseada...
                    </p>
                ) : (
                    <div className="space-y-3">

                        <div>
                            <strong>Nombre:</strong>
                            <p>{parsedBeer.name}</p>
                        </div>

                        <div>
                            <strong>Cervecería:</strong>
                            <p>{parsedBeer.brewery}</p>
                        </div>

                        <div>
                            <strong>Estilo:</strong>
                            <p>{parsedBeer.style}</p>
                        </div>

                        <div>
                            <strong>ABV:</strong>
                            <p>{parsedBeer.abv}</p>
                        </div>

                        <div>
                            <strong>Color:</strong>
                            <p>{parsedBeer.color}</p>
                        </div>

                        <div>
                            <strong>Precios:</strong>
                            <pre>{JSON.stringify(parsedBeer.prices, null, 2)}</pre>
                        </div>

                        <div>
                            <strong>Descripción:</strong>
                            <p>{parsedBeer.description}</p>
                        </div>

                    </div>
                )}
            </div>
        </div>
    );
}