import { useState } from "react";
import Layout from "../layout/Layout";
import TapGrid from "../components/TapGrid";
import { useNavigate } from "react-router-dom";
import museumIcon from "../assets/icons/museum-leviathan-icon-final.png";
import tapListIcon from "../assets/icons/tap-list-icon-transparent.png";
import sortIcon from "../assets/icons/sort-imperial-transparent.png";
import "./Home.css";

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

            <div className="home-controls">
                <button
                    type="button"
                    className="home-controls__museum"
                    aria-label="Museo"
                    onClick={() => navigate("/museum")}
                >
                    <img src={museumIcon} alt="" />
                    <span aria-hidden="true" style={{ height: "15px" }} />
                </button>

                <label className="home-controls__order">
                    <img src={sortIcon} alt="" />
                    <select
                        aria-label="Orden"
                        value={sort}
                        onChange={(e) => setSort(e.target.value)}
                    >
                        <option value="tap">Tap</option>
                        <option value="abv">Alcohol</option>
                        <option value="name">Nombre</option>
                        <option value="style">Estilo</option>
                    </select>
                </label>
            </div>

            <img className="home-catalog-icon" src={tapListIcon} alt="Tap List" />

            {/* 🍺 TAP GRID */}
            <TapGrid sort={sort} />

        </Layout>
    );
}
