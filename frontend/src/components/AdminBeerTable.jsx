const colorLabelMap = {
    "#d88c00": "Ámbar",
    "#e6b800": "Dorado",
    "#111111": "Negro",
    "#8b3a3a": "Rojo",
    "#ff2b5b": "Rosa",
    "#b87333": "Cobrizo"
}

import { updateBeer } from "../api/beers"

export default function AdminBeerTable({ beers, token, refresh, onEdit }) {

    const handleToggle = async (beer) => {
        try {

            await updateBeer(beer.id, {
                ...beer,
                is_available: !beer.is_available
            });

            await refresh();

        } catch (error) {
            console.error("TOGGLE ERROR:", error);
        }
    };

    return (
        <table className="admin-table">

            <thead>
                <tr>
                    <th>Name</th>
                    <th>Style</th>
                    <th>ABV</th>
                    <th>Color</th>
                    <th>Prices</th>
                    <th>On Tap</th>
                    <th>Edit</th>
                </tr>
            </thead>

            <tbody>
                {beers.map((beer) => (
                    <tr key={beer.id}>

                        <td>{beer.name}</td>
                        <td>{beer.style}</td>
                        <td>{beer.abv?.toFixed(1)}%</td>
                        <td>{colorLabelMap[beer.color] || beer.color}</td>

                        <td>
                            {beer.prices
                                ? Object.entries(beer.prices)
                                    .map(([size, price]) => `${size}: $${price}`)
                                    .join(" | ")
                                : "-"}
                        </td>

                        <td>
                            <input
                                type="checkbox"
                                checked={beer.is_available}
                                onChange={() => handleToggle(beer)}
                            />
                        </td>

                        <td>
                            <button onClick={() => onEdit(beer)}>
                                Edit
                            </button>
                        </td>

                    </tr>
                ))}
            </tbody>

        </table>
    )
}