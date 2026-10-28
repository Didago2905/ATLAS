import { uploadTapImage, tapUploadMessage } from "../api/upload";
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

    // ⭐ NUEVO → Featured toggle
    const handleFeaturedToggle = async (beer) => {
        try {
            await updateBeer(beer.id, {
                ...beer,
                is_featured: !beer.is_featured,
                featured_updated_at: Math.floor(Date.now() / 1000)
            });

            await refresh();
        } catch (error) {
            console.error("FEATURED TOGGLE ERROR:", error);
        }
    };

    const [uploadingImages, setUploadingImages] = useState({});
    const handleImageUpload = async (e, beer) => {
        const input = e.target;
        const file = input.files[0];
        if (!file || uploadingImages[beer.id]) return;
        setUploadingImages(prev => ({ ...prev, [beer.id]: true }));
        try {
            const data = await uploadTapImage(beer.id, file, token);
            setLocalBeers(prev => prev.map(b => b.id === beer.id
                ? { ...b, image_url: data.image_url } : b));
            alert(tapUploadMessage(data));
            try {
                await refresh();
            } catch (refreshError) {
                console.error(refreshError);
                alert("La imagen se publicó en ambos destinos, pero falló la actualización de la vista. Recarga la página.");
            }
        } catch (err) {
            alert(err.message || "No se pudo publicar la imagen");
        } finally {
            input.value = "";
            setUploadingImages(prev => ({ ...prev, [beer.id]: false }));
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
                            disabled={Boolean(uploadingImages[beer.id])}
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

                    {/* ⭐ FEATURED */}
                    <div style={{ marginTop: "8px" }}>
                        <span
                            onClick={() => handleFeaturedToggle(beer)}
                            style={{
                                cursor: "pointer",
                                fontSize: "22px",
                                opacity: beer.is_featured ? 1 : 0.35
                            }}
                        >
                            ⭐
                        </span>
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
                        <th>Featured</th>
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
                                    disabled={Boolean(uploadingImages[beer.id])}
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

                            {/* ⭐ FEATURED */}
                            <td>
                                <span
                                    onClick={() => handleFeaturedToggle(beer)}
                                    style={{
                                        cursor: "pointer",
                                        fontSize: "20px",
                                        opacity: beer.is_featured ? 1 : 0.35
                                    }}
                                >
                                    ⭐
                                </span>
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
