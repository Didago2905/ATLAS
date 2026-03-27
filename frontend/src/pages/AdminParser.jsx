import { useState } from "react";
import { parseBeerText, parseMultipleBeers } from "../utils/parser";
import { resolveColor } from "../utils/colorUtils";

// 🔧 Editable inline (UX tipo Notion)
const EditableField = ({ value, onChange }) => {
    const [editing, setEditing] = useState(false);

    const textLength = (value || "").toString().length;

    return editing ? (
        <input
            autoFocus
            value={value || ""}
            onChange={(e) => onChange(e.target.value)}
            onBlur={() => setEditing(false)}
            style={{
                background: "transparent",
                border: "none",
                borderBottom: "1px solid rgba(255,255,255,0.3)",
                color: "white",
                outline: "none",
                width: `${Math.max(textLength * 8, 40)}px`,
                display: "inline-block"
            }}
        />
    ) : (
        <span onClick={() => setEditing(true)} style={{ cursor: "pointer" }}>
            {value || "—"}
        </span>
    );
};

export default function AdminParser() {

    const [inputText, setInputText] = useState("");
    const [parsedData, setParsedData] = useState(null);
    const [formData, setFormData] = useState(null);

    const [isSaving, setIsSaving] = useState(false);
    const [errors, setErrors] = useState({});
    const [warnings, setWarnings] = useState({});
    const [multipleBeers, setMultipleBeers] = useState([]);

    // 🔥 MULTIPARSER STATE
    const [multiErrors, setMultiErrors] = useState({});
    const [multiWarnings, setMultiWarnings] = useState({});
    const [saveResults, setSaveResults] = useState([]);

    const handleParse = () => {
        if (!inputText.trim()) {
            alert("Pega texto primero");
            return;
        }

        const result = parseBeerText(inputText);
        setParsedData(result);
        setFormData(result);

        console.log("🍺 SINGLE PARSE:", result);
    };

    const handleParseMultiple = () => {
        if (!inputText.trim()) {
            alert("Pega texto primero");
            return;
        }

        const beers = parseMultipleBeers(inputText);

        setMultipleBeers(beers);

        setMultiErrors({});
        setMultiWarnings({});
        setSaveResults([]);

        console.log("🍺 RESULTADO MULTIPARSER:", beers);
    };

    const handleChange = (field, value) => {
        setFormData(prev => ({
            ...prev,
            [field]: value
        }));
    };

    const handlePriceChange = (field, value) => {
        setFormData(prev => ({
            ...prev,
            prices: {
                ...prev?.prices,
                [field]: value
            }
        }));
    };

    const validateBeer = (beer, isBulk = false) => {
        const newErrors = {};
        const newWarnings = {};

        if (!beer?.name?.trim()) newErrors.name = "Nombre requerido";
        if (!beer?.brewery?.trim()) newErrors.brewery = "Cervecera requerida";
        if (!beer?.style?.trim()) newErrors.style = "Estilo requerido";

        if (!beer?.description?.trim()) {
            newErrors.description = "Descripción requerida";
        }

        if (beer?.abv) {
            const abvValue = parseFloat(beer.abv);
            if (isNaN(abvValue)) newErrors.abv = "ABV inválido";
        }

        const hasValidPrice = beer?.prices &&
            Object.values(beer.prices).some(v => v !== "" && v !== null && v !== undefined);

        if (!hasValidPrice) {
            if (!isBulk) {
                newErrors.prices = "Debe haber al menos un precio válido";
            }
        }

        const missingPrices = Object.entries(beer?.prices || {})
            .filter(([_, v]) => v === null || v === "" || v === undefined)
            .map(([k]) => k);

        if (missingPrices.length > 0) {
            newWarnings.prices = `Faltan precios: ${missingPrices.join(", ")}`;
        }

        return { errors: newErrors, warnings: newWarnings };
    };

    // 🔥 VALIDACIÓN MASIVA
    const validateAllBeers = (beers) => {
        const errors = {};
        const warnings = {};
        const valids = [];

        beers.forEach((beer, index) => {
            const { errors: e, warnings: w } = validateBeer(beer, true);

            if (Object.keys(e).length > 0) {
                errors[index] = e;
            } else {
                valids.push({ beer, index });
            }

            if (Object.keys(w).length > 0) {
                warnings[index] = w;
            }
        });

        return { errors, warnings, valids };
    };

    const handleSave = async () => {

        if (!formData) return;

        const { errors: validationErrors, warnings: validationWarnings } = validateBeer(formData);

        if (Object.keys(validationErrors).length > 0) {
            setErrors(validationErrors);
            setWarnings({});
            return;
        }

        setErrors({});
        setWarnings(validationWarnings);
        setIsSaving(true);

        try {
            const cleanPrices = Object.fromEntries(
                Object.entries(formData.prices || {})
                    .filter(([_, v]) => v !== "" && v !== null && v !== undefined)
                    .map(([k, v]) => [k, parseFloat(v)])
            );

            const payload = {
                ...formData,
                prices: cleanPrices,
                brewery: formData.brewery,
                origin: formData.origin,
                is_available: true
            };

            const response = await fetch("http://localhost:8001/admin/beers", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${localStorage.getItem("token")}`
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(
                    typeof error.detail === "string"
                        ? error.detail
                        : JSON.stringify(error.detail)
                );
            }

            alert("🍺 Cerveza guardada correctamente");

            setFormData(null);
            setParsedData(null);
            setInputText("");

        } catch (error) {
            console.error(error);
            alert(error.message);
        } finally {
            setIsSaving(false);
        }
    };

    // 🔥 GUARDAR TODAS
    const handleSaveAll = async () => {

        if (!multipleBeers.length) return;

        const { errors, warnings, valids } = validateAllBeers(multipleBeers);

        setMultiErrors(errors);
        setMultiWarnings(warnings);

        if (valids.length === 0) {
            console.warn("⚠️ No hay válidas según validación, intentando guardar todas...");
        }

        const results = [];

        for (let index = 0; index < multipleBeers.length; index++) {
            const beer = multipleBeers[index];

            console.log("🚀 Guardando cerveza:", beer.name);

            try {
                const cleanPrices = Object.fromEntries(
                    Object.entries(beer.prices || {})
                        .filter(([_, v]) => v !== "" && v !== null && v !== undefined)
                        .map(([k, v]) => [k, parseFloat(v)])
                );

                const payload = {
                    ...beer,
                    prices: cleanPrices,
                    brewery: beer.brewery,
                    origin: beer.origin,
                    is_available: true
                };

                const response = await fetch("http://localhost:8001/admin/beers", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${localStorage.getItem("token")}`
                    },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) throw new Error();

                results.push({ index, status: "success" });

            } catch {
                results.push({ index, status: "error" });
            }
        }

        setSaveResults(results);

        setSaveResults(results);

        console.log("✅ Total intentadas:", multipleBeers.length);
        console.log("✅ Guardadas:", results.filter(r => r.status === "success").length);

        alert(`🍺 Guardadas: ${results.filter(r => r.status === "success").length}`);

        alert(`🍺 Guardadas: ${results.filter(r => r.status === "success").length}`);

    };

    const previewColor = formData?.color
        ? resolveColor(formData.color)
        : "#444";

    return (
        <div style={{ width: "100%", color: "white" }}>

            <h2>Parser</h2>

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

            <div style={{ display: "flex", gap: "10px" }}>
                <button onClick={handleParse}>
                    Parse (1 cerveza)
                </button>

                <button onClick={handleParseMultiple}>
                    Parse MASIVO 🚀
                </button>
            </div>

            {/* MULTIPARSER */}
            {multipleBeers.length > 0 && (
                <div style={{
                    marginTop: "20px",
                    maxHeight: "70vh",
                    overflowY: "auto",
                    background: "#111",
                    padding: "10px",
                    borderTop: "1px solid rgba(255,255,255,0.2)"
                }}>
                    <h3>🍺 Cervezas detectadas ({multipleBeers.length})</h3>

                    {multipleBeers.map((beer, i) => {

                        const previewColor = beer?.color
                            ? resolveColor(beer.color)
                            : "#444";

                        // 🔥 CORRECTO: fuera del style
                        const hasError = multiErrors[i];
                        const hasWarning = multiWarnings[i];

                        return (
                            <div
                                key={i}
                                style={{
                                    border: hasError
                                        ? "2px solid #ff4d4f"
                                        : hasWarning
                                            ? "2px solid #ffd166"
                                            : "1px solid rgba(255,255,255,0.2)",
                                    padding: "15px",
                                    marginBottom: "15px",
                                    borderRadius: "8px",
                                    background: "#111"
                                }}
                            >

                                {/* NAME */}
                                <h3>
                                    🍺{" "}
                                    <EditableField
                                        value={beer.name}
                                        onChange={(v) => {
                                            const updated = [...multipleBeers];
                                            updated[i].name = v;
                                            setMultipleBeers(updated);
                                        }}
                                    />
                                </h3>

                                {/* INFO */}
                                <div>
                                    🏭{" "}
                                    <EditableField
                                        value={beer.brewery}
                                        onChange={(v) => {
                                            const updated = [...multipleBeers];
                                            updated[i].brewery = v;
                                            setMultipleBeers(updated);
                                        }}
                                    />
                                </div>

                                <div>
                                    🌍{" "}
                                    <EditableField
                                        value={beer.origin}
                                        onChange={(v) => {
                                            const updated = [...multipleBeers];
                                            updated[i].origin = v;
                                            setMultipleBeers(updated);
                                        }}
                                    />
                                </div>

                                <div>
                                    🎨{" "}
                                    <EditableField
                                        value={beer.style?.replace(/ABV:.*/i, "").trim()}
                                        onChange={(v) => {
                                            const updated = [...multipleBeers];
                                            updated[i].style = v;
                                            setMultipleBeers(updated);
                                        }}
                                    />
                                </div>

                                <div>
                                    🍻{" "}
                                    <EditableField
                                        value={beer.abv}
                                        onChange={(v) => {
                                            const updated = [...multipleBeers];
                                            updated[i].abv = v;
                                            setMultipleBeers(updated);
                                        }}
                                    />
                                </div>

                                <div>
                                    🎨{" "}
                                    <EditableField
                                        value={beer.color?.replace(/PRECIOS:.*/i, "").trim()}
                                        onChange={(v) => {
                                            const updated = [...multipleBeers];
                                            updated[i].color = v;
                                            setMultipleBeers(updated);
                                        }}
                                    />

                                    <span style={{
                                        marginLeft: "10px",
                                        width: "12px",
                                        height: "12px",
                                        borderRadius: "50%",
                                        display: "inline-block",
                                        background: previewColor,
                                        border: "1px solid rgba(255,255,255,0.4)"
                                    }} />
                                </div>

                                {/* PRECIOS */}
                                <div style={{ marginTop: "10px" }}>
                                    💰
                                    <ul>
                                        {Object.entries(beer.prices || {}).map(([key, value]) => (
                                            <li key={key}>
                                                {key}:{" "}
                                                <EditableField
                                                    value={value}
                                                    onChange={(v) => {
                                                        const updated = [...multipleBeers];
                                                        updated[i].prices[key] = v;
                                                        setMultipleBeers(updated);
                                                    }}
                                                />
                                            </li>
                                        ))}
                                    </ul>
                                </div>

                                {/* DESCRIPCIÓN */}
                                <textarea
                                    value={beer.description || ""}
                                    onChange={(e) => {
                                        const updated = [...multipleBeers];
                                        updated[i].description = e.target.value;
                                        setMultipleBeers(updated);
                                    }}
                                    style={{
                                        width: "100%",
                                        minHeight: "100px",
                                        background: "transparent",
                                        border: "none",
                                        color: "white",
                                        marginTop: "10px"
                                    }}
                                />

                                {/* 🔥 ERRORES */}
                                {multiErrors[i] && (
                                    <div style={{ color: "#ff4d4f", marginTop: "10px" }}>
                                        {Object.values(multiErrors[i]).map((e, idx) => (
                                            <div key={idx}>⚠️ {e}</div>
                                        ))}
                                    </div>
                                )}

                                {/* 🔥 WARNINGS */}
                                {multiWarnings[i] && (
                                    <div style={{ color: "#ffd166", marginTop: "10px" }}>
                                        {Object.values(multiWarnings[i]).map((w, idx) => (
                                            <div key={idx}>⚠️ {w}</div>
                                        ))}
                                    </div>
                                )}

                                {/* 🔥 RESULTADO */}
                                {saveResults.find(r => r.index === i)?.status === "success" && (
                                    <div style={{ color: "#4caf50", marginTop: "10px" }}>
                                        ✅ Guardada
                                    </div>
                                )}

                            </div>
                        );
                    })}
                </div>

            )}

            {/* 🔥 UI ORIGINAL RESTAURADA */}
            {/* 🍺 RESULTADO EDITABLE COMPLETO */}
            {formData && (
                <div style={{
                    marginTop: "20px",
                    padding: "20px",
                    borderRadius: "8px",
                    background: "#111"
                }}>

                    {/* NAME */}
                    <h2>
                        🍺{" "}
                        <EditableField
                            value={formData.name}
                            onChange={(v) => handleChange("name", v)}
                        />
                    </h2>

                    {/* INFO */}
                    <div>
                        🏭 <strong>Cervecería:</strong>{" "}
                        <EditableField
                            value={formData.brewery}
                            onChange={(v) => handleChange("brewery", v)}
                        />
                    </div>

                    <div>
                        🎨 <strong>Estilo:</strong>{" "}
                        <EditableField
                            value={formData.style}
                            onChange={(v) => handleChange("style", v)}
                        />
                    </div>

                    <div>
                        🍻 <strong>ABV:</strong>{" "}
                        <EditableField
                            value={formData.abv}
                            onChange={(v) => handleChange("abv", v)}
                        />
                    </div>

                    <div>
                        🎨 <strong>Color:</strong>{" "}
                        <EditableField
                            value={formData.color}
                            onChange={(v) => handleChange("color", v)}
                        />

                        {/* preview */}
                        <span style={{
                            marginLeft: "10px",
                            width: "12px",
                            height: "12px",
                            borderRadius: "50%",
                            display: "inline-block",
                            background: previewColor,
                            border: "1px solid rgba(255,255,255,0.4)"
                        }} />
                    </div>

                    {/* 💰 PRECIOS */}
                    <div style={{ marginTop: "15px" }}>
                        <strong>💰 Precios:</strong>

                        <ul style={{ marginTop: "5px" }}>
                            <li>
                                Taster:{" "}
                                <EditableField
                                    value={formData.prices?.taster}
                                    onChange={(v) => handlePriceChange("taster", v)}
                                />
                            </li>

                            <li>
                                Pinta chica:{" "}
                                <EditableField
                                    value={formData.prices?.pinta_chica}
                                    onChange={(v) => handlePriceChange("pinta_chica", v)}
                                />
                            </li>

                            <li>
                                Pinta grande:{" "}
                                <EditableField
                                    value={formData.prices?.pinta_grande}
                                    onChange={(v) => handlePriceChange("pinta_grande", v)}
                                />
                            </li>

                            <li>
                                Jarra chica:{" "}
                                <EditableField
                                    value={formData.prices?.jarra_chica}
                                    onChange={(v) => handlePriceChange("jarra_chica", v)}
                                />
                            </li>

                            <li>
                                Jarra grande:{" "}
                                <EditableField
                                    value={formData.prices?.jarra_grande}
                                    onChange={(v) => handlePriceChange("jarra_grande", v)}
                                />
                            </li>
                        </ul>
                    </div>

                    {/* 📝 DESCRIPCIÓN */}
                    <div style={{ marginTop: "25px", maxWidth: "800px" }}>
                        <div style={{
                            marginBottom: "8px",
                            opacity: 0.8,
                            fontSize: "14px"
                        }}>
                            📝 Descripción
                        </div>

                        <textarea
                            value={formData.description || ""}
                            onChange={(e) => handleChange("description", e.target.value)}
                            style={{
                                width: "100%",
                                minHeight: "140px",
                                background: "transparent",
                                border: "none",
                                color: "white",
                                padding: "0",
                                outline: "none",
                                fontSize: "16px",
                                lineHeight: "1.7"
                            }}
                        />
                    </div>

                    {/* ⚠️ ERRORES */}
                    {Object.keys(errors).length > 0 && (
                        <div style={{ marginTop: "15px", color: "#ff6b6b" }}>
                            {Object.values(errors).map((err, i) => (
                                <div key={i}>⚠️ {err}</div>
                            ))}
                        </div>
                    )}

                    {/* ⚠️ WARNINGS */}
                    {Object.keys(warnings).length > 0 && (
                        <div style={{ marginTop: "10px", color: "#ffd166" }}>
                            {Object.values(warnings).map((warn, i) => (
                                <div key={i}>⚠️ {warn}</div>
                            ))}
                        </div>
                    )}

                </div>
            )}

            {/* BOTÓN */}
            {formData && (
                <div style={{ marginTop: "20px" }}>
                    <button onClick={handleSave} disabled={isSaving}>
                        {isSaving ? "Guardando..." : "Guardar cerveza 🍺"}
                    </button>
                </div>
            )}

            {multipleBeers.length > 0 && (
                <div style={{ marginTop: "20px" }}>
                    <button onClick={handleSaveAll}>
                        Guardar todas 🍺
                    </button>
                </div>
            )}

        </div>
    );
}