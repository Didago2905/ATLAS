import { formatABV } from "../utils/formatters";
import { resolveColor, colorLabelMap } from "../utils/colorUtils";

// 🔥 detectar si el color es oscuro (luminancia real)
const isDarkColor = (hex) => {
    if (!hex || !hex.startsWith("#")) return false;

    const r = parseInt(hex.substr(1, 2), 16);
    const g = parseInt(hex.substr(3, 2), 16);
    const b = parseInt(hex.substr(5, 2), 16);

    const luminance = (0.299 * r + 0.587 * g + 0.114 * b);

    return luminance < 60;
};

// 🔥 ajustar color solo si es demasiado oscuro
const adjustColorForUI = (hex) => {
    if (isDarkColor(hex)) {
        return "#444444"; // gris visible pero coherente
    }
    return hex;
};

export default function BeerCard({ beer }) {

    // 🔥 color base
    const rawColor = resolveColor(beer.color);

    // 🔥 color ajustado para UI
    const beerColor = adjustColorForUI(rawColor);

    // 🔥 label
    const colorLabel =
        colorLabelMap[rawColor] || beer.color;

    return (
        <div
            className="beer-card"
            style={{
                borderTop: `6px solid ${beerColor}`,
                boxShadow: `0 0 6px ${beerColor}` // 🔥 glow sutil
            }}
        >

            <h2>{beer.name}</h2>

            <p><strong>Style:</strong> {beer.style}</p>
            <p><strong>ABV:</strong> {formatABV(beer.abv)}</p>

            {beer.color && (
                <p><strong>Color:</strong> {colorLabel}</p>
            )}

            {beer.description && (
                <p className="beer-description">
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

        </div>
    )
}