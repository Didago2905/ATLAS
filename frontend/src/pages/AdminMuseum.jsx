import { useState } from "react";
import { uploadImage } from "../api/upload";

export default function AdminMuseum() {

    const [file, setFile] = useState(null);
    const [type, setType] = useState("fichas/antiguas");
    const [preview, setPreview] = useState(null);
    const [loading, setLoading] = useState(false);

    // 🔥 NUEVOS STATES (metadata)
    const [name, setName] = useState("");
    const [style, setStyle] = useState("");
    const [abv, setAbv] = useState("");
    const [year, setYear] = useState("");

    const handleFile = (e) => {
        const selected = e.target.files[0];
        if (!selected) return;

        setFile(selected);
        setPreview(URL.createObjectURL(selected));
    };

    const handleUpload = async () => {
        if (!file) return alert("Selecciona una imagen");

        setLoading(true);

        try {
            // 🔥 payload de metadata (por ahora solo debug)
            const payload = {
                name,
                style,
                abv,
                year,
                type,
            };

            console.log("📦 DATA:", payload);

            const res = await uploadImage(file, type, {
                name,
                style,
                abv,
                year,
            });

            alert("✅ Imagen subida correctamente");
            console.log("🖼 URL:", res.image_url);

            // reset
            setFile(null);
            setPreview(null);
            setName("");
            setStyle("");
            setAbv("");
            setYear("");

        } catch (err) {
            console.error(err);
            alert("❌ Error al subir imagen");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div>

            <h1>Uploader Museo 🏛</h1>

            {/* 🔽 selector tipo */}
            <div style={{ marginBottom: "15px" }}>
                <select
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                >
                    <option value="fichas/antiguas">Fichas Antiguas</option>
                    <option value="fichas/actuales">Fichas Actuales</option>
                    <option value="tap">Tap</option>
                    <option value="botellas">Botellas</option>
                </select>
            </div>

            {/* 📁 input */}
            <input
                type="file"
                accept="image/*"
                onChange={handleFile}
            />

            {/* 🖼 preview */}
            {preview && (
                <div style={{ marginTop: "15px" }}>
                    <img
                        src={preview}
                        alt="preview"
                        style={{
                            width: "200px",
                            borderRadius: "10px"
                        }}
                    />
                </div>
            )}

            {/* 🔥 METADATA FORM */}
            {preview && (
                <div style={{ marginTop: "15px", display: "flex", flexDirection: "column", gap: "10px", maxWidth: "300px" }}>

                    <input
                        type="text"
                        placeholder="Nombre"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                    />

                    <input
                        type="text"
                        placeholder="Estilo"
                        value={style}
                        onChange={(e) => setStyle(e.target.value)}
                    />

                    <input
                        type="number"
                        placeholder="ABV"
                        value={abv}
                        onChange={(e) => setAbv(e.target.value)}
                    />

                    <input
                        type="number"
                        placeholder="Año"
                        value={year}
                        onChange={(e) => setYear(e.target.value)}
                    />

                </div>
            )}

            {/* 🚀 botón */}
            <div style={{ marginTop: "15px" }}>
                <button onClick={handleUpload} disabled={loading}>
                    {loading ? "Subiendo..." : "Subir imagen 🚀"}
                </button>
            </div>

        </div>
    );
}