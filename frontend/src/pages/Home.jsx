import { useState } from "react";
import Layout from "../layout/Layout";
import TapGrid from "../components/TapGrid";

export default function Home() {

    const [sort, setSort] = useState("tap");

    return (
        <Layout>

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