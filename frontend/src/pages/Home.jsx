import { useState } from "react";
import Layout from "../layout/Layout";
import BeerList from "../components/BeerList";
import { usePublicBeers } from "../hooks/usePublicBeers";

export default function Home() {

    const { beers } = usePublicBeers();

    const [search, setSearch] = useState("");

    const filteredBeers = beers.filter(beer =>
        beer.name.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <Layout>

            {/* 🔍 Buscador */}
            <input
                type="text"
                placeholder="Buscar cerveza..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                    marginBottom: "20px",
                    padding: "10px",
                    width: "300px",
                    borderRadius: "8px",
                    border: "1px solid #333",
                    background: "#111",
                    color: "#fff"
                }}
            />

            {/* 📊 Contador opcional */}
            <p style={{ opacity: 0.6 }}>
                {filteredBeers.length} resultados
            </p>

            <BeerList beers={filteredBeers} />

        </Layout>
    );
}