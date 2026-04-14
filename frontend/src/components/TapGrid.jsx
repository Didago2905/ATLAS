import { useState, useEffect } from "react";
import useTapBeers from "../hooks/useTapBeers";
import BeerCard from "./BeerCard";
import { useNavigate } from "react-router-dom";

export default function TapGrid({ sort }) {
    const beers = useTapBeers();
    const navigate = useNavigate();
    const [exiting, setExiting] = useState(false);

    // 🔥 ORDEN
    const sortedBeers = [...beers].sort((a, b) => {
        if (sort === "abv") return (b.abv || 0) - (a.abv || 0);
        if (sort === "name") return a.name.localeCompare(b.name);
        if (sort === "style") return a.style.localeCompare(b.style);
        return (a.tap_position || 999) - (b.tap_position || 999);
    });

    // 🔥 TAP FIJO (16)
    const maxSlots = 16;
    const tapBeers = sortedBeers.slice(0, maxSlots);

    const filledBeers = [...tapBeers];
    while (filledBeers.length < maxSlots) {
        filledBeers.push(null);
    }

    const isLoading = beers.length === 0;

    return (
        <div
            style={{
                padding: "20px",

                opacity: exiting ? 0 : 1,
                transform: exiting ? "scale(0.96)" : "scale(1)",
                transition: "all 0.28s cubic-bezier(0.22, 1, 0.36, 1)",
            }}
        >
            {/* GRID TAP */}
            <div
                style={{
                    display: "grid",
                    gridTemplateColumns:
                        window.innerWidth < 600
                            ? "repeat(2, 1fr)"
                            : window.innerWidth < 900
                                ? "repeat(3, 1fr)"
                                : "repeat(4, 1fr)",
                    gap: "12px",
                    width: "100%",
                }}
            >
                {isLoading
                    ? Array.from({ length: 16 }).map((_, index) => (
                        <div
                            key={`skeleton-${index}`}
                            style={{
                                aspectRatio: "3/4",
                                borderRadius: "12px",
                                background: "linear-gradient(90deg, #222, #333, #222)",
                                backgroundSize: "200% 100%",
                                animation: "shimmer 1.5s infinite",
                            }}
                        />
                    ))
                    : filledBeers.map((beer, index) => {

                        // 🔥 SLOT VACÍO
                        if (!beer) {
                            return (
                                <div
                                    key={index}
                                    style={{
                                        aspectRatio: "3/4",
                                        borderRadius: "12px",
                                        background: "rgba(255,255,255,0.05)",
                                        border: "1px dashed rgba(255,255,255,0.1)",
                                    }}
                                />
                            );
                        }

                        // 🔥 SLOT CON CERVEZA
                        return (
                            <div
                                key={`${beer.id}-${index}`}
                                onClick={() => {
                                    setExiting(true);

                                    setTimeout(() => {
                                        navigate(`/beer/${beer.id}`);
                                    }, 280); // 🔥 tiempo alineado con animación
                                }}
                                style={{
                                    position: "relative",
                                    aspectRatio: "3/4",
                                    borderRadius: "12px",
                                    overflow: "hidden",
                                    cursor: "pointer",
                                    display: "flex",
                                    flexDirection: "column",
                                    justifyContent: "flex-end",
                                    background: "#111", // 🔥 antes era url()
                                    boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                                    transition: "transform 0.2s ease",
                                }}
                                onMouseEnter={(e) =>
                                    (e.currentTarget.style.transform = "scale(1.03)")
                                }
                                onMouseLeave={(e) =>
                                    (e.currentTarget.style.transform = "scale(1)")
                                }
                            >

                                {/* 🔥 IMAGEN LAZY + FADE */}
                                {beer.image_url && (
                                    <img
                                        src={beer.image_url}
                                        alt={beer.name}
                                        loading="lazy"
                                        style={{
                                            position: "absolute",
                                            top: 0,
                                            left: 0,
                                            width: "100%",
                                            height: "100%",
                                            objectFit: "contain",
                                            opacity: 0,
                                            transition: "opacity 0.4s ease",
                                        }}
                                        onLoad={(e) => {
                                            e.target.style.opacity = 1;
                                        }}
                                    />
                                )}

                                {/* INFO SI NO HAY IMAGEN */}
                                {!beer.image_url && (
                                    <div
                                        style={{
                                            padding: "10px",
                                            background: "rgba(0,0,0,0.6)",
                                            color: "#fff",
                                            fontSize: "14px",
                                        }}
                                    >
                                        <strong>{beer.name}</strong>
                                        <div style={{ opacity: 0.7 }}>{beer.style}</div>
                                        <div style={{ fontSize: "12px", opacity: 0.6 }}>
                                            {beer.abv}% ABV
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
            </div>

        </div>
    );
}