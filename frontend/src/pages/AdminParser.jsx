import { useState } from "react";
import { parseBeerText } from "../utils/parser"; // 🔥 IMPORT NUEVO

export default function AdminParser() {

    const [inputText, setInputText] = useState("");
    const [parsedData, setParsedData] = useState(null);

    const handleParse = () => {

        if (!inputText.trim()) {
            alert("Pega texto primero");
            return;
        }

        const result = parseBeerText(inputText); // 🔥 USAMOS EL PARSER REAL

        console.log("Parsed result:", result); // 👈 debug útil

        setParsedData(result);
    };

    return (
        <div style={{ width: "100%" }}>

            <h2>Parser</h2>

            {/* 📝 INPUT */}
            <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="Pega aquí la ficha de la cerveza..."
                style={{
                    width: "100%",
                    height: "150px",
                    marginBottom: "10px",
                    padding: "10px",
                    borderRadius: "6px"
                }}
            />

            {/* 🔘 BOTÓN */}
            <button onClick={handleParse}>
                Parse
            </button>

            {/* 📦 OUTPUT */}
            {parsedData && (
                <pre style={{
                    marginTop: "20px",
                    background: "#111",
                    padding: "15px",
                    borderRadius: "6px",
                    overflowX: "auto"
                }}>
                    {JSON.stringify(parsedData, null, 2)}
                </pre>
            )}

        </div>
    );
}