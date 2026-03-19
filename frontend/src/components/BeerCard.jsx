import { formatABV } from "../utils/formatters";

const colorMap = {
    "Ámbar": "#d88c00",
    "Dorado": "#e6b800",
    "Negro": "#111111",
    "Rojo": "#8b3a3a",
    "Rosa": "#ff2b5b",
    "Cobrizo": "#b87333",

    "#d88c00": "#d88c00",
    "#e6b800": "#e6b800",
    "#111111": "#111111",
    "#8b3a3a": "#8b3a3a",
    "#ff2b5b": "#ff2b5b",
    "#b87333": "#b87333"
}

const colorLabelMap = {
    "#d88c00": "Ámbar",
    "#e6b800": "Dorado",
    "#111111": "Negro",
    "#8b3a3a": "Rojo",
    "#ff2b5b": "Rosa",
    "#b87333": "Cobrizo"
}

export default function BeerCard({ beer }) {

    const beerColor =
        colorMap[beer.color] || (beer.color?.startsWith("#") ? beer.color : "#444")

    const normalizedColor = beer.color?.trim().toLowerCase()
    const colorLabel = colorLabelMap[normalizedColor] || beer.color

    return (
        <div
            className="beer-card"
            style={{ borderTop: `6px solid ${beerColor}` }}
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