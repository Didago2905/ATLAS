
import { colorLabelMap } from "../utils/colorUtils";
import { updateBeer } from "../api/beers";
import { useState, useEffect } from "react";

export default function AdminBeerTable({ beers, token, refresh, onEdit }) {

    const [localBeers, setLocalBeers] = useState(beers);

    useEffect(() => {
        setLocalBeers(beers);
    }, [beers]);

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

    // 🟠 FASE 1 → preview inmediato
    const handleImageUpload = async (e, beer) => {
        const file = e.target.files[0];
        if (!file) return;

        // preview inmediato
        const imageUrl = URL.createObjectURL(file);

        const updated = localBeers.map(b =>
            b.id === beer.id ? { ...b, image_url: imageUrl } : b
        );

        setLocalBeers(updated);

        // 🔥 upload real
        const formData = new FormData();
        formData.append("file", file);

        try {
            await fetch(`/api/admin/beers/${beer.id}/upload-image`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`
                },
                body: formData
            });

            await refresh(); // 🔥 recarga desde DB
        } catch (err) {
            console.error("UPLOAD ERROR:", err);
        }
    };

    // 🟣 FASE 2 → preparado para backend
    const handleSaveImage = async (beer, file) => {
        try {
            const formData = new FormData();
            formData.append("file", file);

            await fetch(`/api/admin/beers/${beer.id}/upload-image`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`
                },
                body: formData
            });

            await refresh();
        } catch (err) {
            console.error("UPLOAD ERROR:", err);
        }
    };

    const isMobile = window.innerWidth < 768;

    return isMobile ? (

        // 🔵 MOBILE → CARDS
        <div style={{ padding: "10px" }}>
            {localBeers.map((beer) => (
                <div
                    key={beer.id}
                    style={{
                        background: "#111",
                        padding: "12px",
                        borderRadius: "10px",
                        marginBottom: "10px"
                    }}
                >
                    <strong>{beer.name}</strong>
                    <div>{beer.style}</div>
                    <div>{beer.abv?.toFixed(1)}%</div>
                    <div>{colorLabelMap[beer.color] || beer.color}</div>

                    {/* precios */}
                    <div style={{ marginTop: "6px", fontSize: "12px", opacity: 0.7 }}>
                        {beer.prices
                            ? Object.entries(beer.prices)
                                .map(([size, price]) => `${size}: $${price}`)
                                .join(" | ")
                            : "-"}
                    </div>

                    {/* imagen */}
                    {beer.image_url && (
                        <img
                            src={beer.image_url}
                            alt=""
                            style={{
                                width: "60px",
                                marginTop: "8px",
                                borderRadius: "6px"
                            }}
                        />
                    )}

                    {/* upload */}
                    <div style={{ marginTop: "8px" }}>
                        <input
                            type="file"
                            accept="image/*"
                            onChange={(e) => handleImageUpload(e, beer)}
                            style={{ display: "none" }}
                            id={`file-${beer.id}`}
                        />

                        <label
                            htmlFor={`file-${beer.id}`}
                            style={{
                                padding: "6px 10px",
                                background: "#333",
                                color: "#fff",
                                borderRadius: "6px",
                                fontSize: "12px",
                                cursor: "pointer"
                            }}
                        >
                            {beer.image_url ? "Cambiar imagen" : "Subir imagen"}
                        </label>
                    </div>

                    {/* toggle */}
                    <div style={{ marginTop: "8px" }}>
                        <label>
                            <input
                                type="checkbox"
                                checked={beer.is_available}
                                onChange={() => handleToggle(beer)}
                            />
                            {" "}On Tap
                        </label>
                    </div>

                    {/* edit */}
                    <button
                        onClick={() => onEdit(beer)}
                        style={{ marginTop: "8px" }}
                    >
                        Edit
                    </button>
                </div>
            ))}
        </div>

    ) : (

        // 🟢 DESKTOP → TABLA ORIGINAL
        <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
            <table
                className="admin-table"
                style={{ minWidth: "800px" }}
            >

                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Style</th>
                        <th>ABV</th>
                        <th>Color</th>
                        <th>Prices</th>
                        <th>Image</th>
                        <th>On Tap</th>
                        <th>Edit</th>
                    </tr>
                </thead>

                <tbody>
                    {localBeers.map((beer, index) => (
                        <tr
                            key={beer.id}
                            style={{
                                backgroundColor: index % 2 === 0 ? "#000" : "#1a1a1a"
                            }}
                        >

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

                            {/* IMAGE */}
                            <td>
                                <input
                                    type="file"
                                    accept="image/*"
                                    onChange={(e) => handleImageUpload(e, beer)}
                                    style={{ display: "none" }}
                                    id={`file-${beer.id}`}
                                />

                                <label
                                    htmlFor={`file-${beer.id}`}
                                    style={{
                                        display: "inline-block",
                                        padding: "6px 10px",
                                        background: "#333",
                                        color: "#fff",
                                        borderRadius: "6px",
                                        cursor: "pointer",
                                        fontSize: "12px"
                                    }}
                                >
                                    {beer.image_url ? "Cambiar imagen" : "Subir imagen"}
                                </label>

                                {beer.image_url && (
                                    <div style={{ marginTop: "6px" }}>
                                        <img
                                            src={beer.image_url}
                                            alt=""
                                            style={{
                                                width: "50px",
                                                height: "70px",
                                                objectFit: "contain",
                                                borderRadius: "6px"
                                            }}
                                        />
                                    </div>
                                )}
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
        </div>

    );
}