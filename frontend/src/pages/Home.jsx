import { useState } from "react";
import Layout from "../layout/Layout";
import TapGrid from "../components/TapGrid";
import { useNavigate } from "react-router-dom";

export default function Home() {

    const navigate = useNavigate(); // 🔥 NUEVO

    const [sort, setSort] = useState(() => {
        const saved = localStorage.getItem("tapFilter");
        if (saved) {
            try {
                return JSON.parse(saved).sort || "tap";
            } catch {
                return "tap";
            }
        }
        return "tap";
    });

    return (
        <Layout>

            {/* 🏛 MUSEO */}
            <div style={{ marginBottom: "12px" }}>
                <button
                    onClick={() => navigate("/museum")}
                    style={{
                        width: "100%",
                        padding: "12px",
                        borderRadius: "10px",
                        background: "#111",
                        color: "#fff",
                        border: "1px solid #333",
                        cursor: "pointer",
                        fontSize: "14px",
                        opacity: 0.85
                    }}
                >
                    🏛 Explorar modo museo
                </button>
            </div>

            {/* 🎛️ CONTROL SIMPLE */}
            <div style={{ marginBottom: "20px" }}>
                <select
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                    style={{
                        padding: "10px",
                        borderRadius: "8px",
                        background: "#111",
                        color: "#fff",
                        border: "1px solid #333"
                    }}
                >
                    <option value="tap">Orden del Tap</option>
                    <option value="abv">Alcohol</option>
                    <option value="name">Nombre</option>
                    <option value="style">Estilo</option>
                </select>
            </div>

            {/* 🍺 TAP GRID */}
            <TapGrid sort={sort} />

        </Layout>
    );
}