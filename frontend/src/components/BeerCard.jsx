import { formatABV } from "../utils/formatters";
import { resolveColor, colorLabelMap } from "../utils/colorUtils";
import { useState, useRef, useEffect } from "react";

// 🔥 detectar si el color es oscuro
const isDarkColor = (hex) => {
    if (!hex || !hex.startsWith("#")) return false;

    const r = parseInt(hex.substr(1, 2), 16);
    const g = parseInt(hex.substr(3, 2), 16);
    const b = parseInt(hex.substr(5, 2), 16);

    const luminance = (0.299 * r + 0.587 * g + 0.114 * b);
    return luminance < 60;
};

// 🔥 ajustar color
const adjustColorForUI = (hex) => {
    if (isDarkColor(hex)) {
        return "#444444";
    }
    return hex;
};

export default function BeerCard({ beer }) {

    const [showBrewery, setShowBrewery] = useState(false);
    const panelRef = useRef(null); // 🔥 AQUÍ VA

    // 🔥 click fuera
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (panelRef.current && !panelRef.current.contains(event.target)) {
                setShowBrewery(false);
            }
        };

        document.addEventListener("mousedown", handleClickOutside);

        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, []);

    const rawColor = resolveColor(beer.color);
    const beerColor = adjustColorForUI(rawColor);

    const colorLabel =
        colorLabelMap[rawColor] || beer.color;

    const breweryLogos = {
        tiburon: "/logos/tiburon.png",
        invitada: "/logos/invitada.png",
        default: "/logos/default.png"
    };

    const breweryInfo = {
        tiburon: {
            name: "Tiburón Brewing Co.",
            location: "Xalapa, México",
            type: "Artesanal",
            description: "Especialidad en IPAs intensas"
        },
        invitada: {
            name: "Cervecería Invitada",
            location: "México",
            type: "Invitada",
            description: "Selección rotativa"
        },
        default: {
            name: "Cervecería",
            location: "",
            type: "",
            description: ""
        }
    };

    const normalize = (str) =>
        str
            ?.toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");

    const breweryKey = normalize(beer.brewery) || "default";
    const logo = breweryLogos[breweryKey] || breweryLogos.default;
    const brewery = breweryInfo[breweryKey] || breweryInfo.default;

    return (
        <div
            className="beer-card"
            style={{
                position: "relative",
                height: "100%",            // 🔥 ocupa todo el contenedor
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between", // 🔥 distribuye contenido
                borderTop: `6px solid ${beerColor}`,
                boxShadow: `0 0 6px ${beerColor}`
            }}
        >

            <h2>{beer.name}</h2>

            <p><strong>Style:</strong> {beer.style}</p>
            <p><strong>ABV:</strong> {formatABV(beer.abv)}</p>

            {beer.color && (
                <p><strong>Color:</strong> {colorLabel}</p>
            )}

            {beer.description && (
                <p
                    className="beer-description"
                    style={{
                        flexGrow: 1,
                        overflow: "hidden",
                    }}
                >
                    {beer.description}
                </p>
            )}

            <div className="beer-prices">
                {beer.prices ? (
                    Object.entries(beer.prices).map(([size, price]) => (
                        <p key={size}>
                            {size.replace("_", " ")}: ${price}
                        </p>
                    ))
                ) : (
                    <p>No prices</p>
                )}
            </div>

            {/* 🔥 SELLO */}
            <img
                onClick={(e) => {
                    e.stopPropagation(); // 🔥 evita cierre inmediato
                    setShowBrewery(prev => !prev);
                }}
                src={logo}
                alt="brewery"
                style={{
                    position: "absolute",
                    bottom: "10px",
                    right: "10px",
                    width: "70px",
                    opacity: 0.2,
                    cursor: "pointer",
                    userSelect: "none",
                    filter: "grayscale(100%) contrast(1.2)"
                }}
            />

            {/* 🔥 PANEL */}
            <div
                ref={panelRef}
                style={{
                    position: "absolute",
                    bottom: "90px",
                    right: "10px",
                    width: "180px",
                    background: "rgba(0,0,0,0.9)",
                    color: "#fff",
                    padding: "10px",
                    borderRadius: "8px",
                    fontSize: "12px",
                    zIndex: 20,

                    opacity: showBrewery ? 1 : 0,
                    transform: showBrewery
                        ? "translateY(0px)"
                        : "translateY(10px)",
                    pointerEvents: showBrewery ? "auto" : "none",
                    transition: "all 0.2s ease"
                }}
            >
                <strong>{brewery.name}</strong>

                {brewery.location && (
                    <div style={{ opacity: 0.7 }}>
                        {brewery.location}
                    </div>
                )}

                {brewery.type && (
                    <div style={{ marginTop: "4px" }}>
                        {brewery.type}
                    </div>
                )}

                {brewery.description && (
                    <div style={{ opacity: 0.7, marginTop: "6px" }}>
                        {brewery.description}
                    </div>
                )}

                <div
                    style={{
                        marginTop: "8px",
                        textDecoration: "underline",
                        cursor: "pointer"
                    }}
                >
                    Ver más
                </div>
            </div>

        </div>
    );
}