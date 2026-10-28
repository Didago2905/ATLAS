export async function uploadImage(file, type, metadata) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("type", type);

    // 🔥 metadata
    formData.append("name", metadata.name);
    formData.append("style", metadata.style);
    formData.append("abv", metadata.abv);
    formData.append("year", metadata.year);

    const res = await fetch("/api/admin/museum", {
        method: "POST",
        headers: {
            Authorization: `Bearer ${localStorage.getItem("token")}`
        },
        body: formData
    });

    if (res.status === 401) {
        localStorage.removeItem("token");
        window.location.href = "/login";
        throw new Error("Sesión expirada. Inicia sesión de nuevo.");
    }

    if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(typeof error.detail === "string" ? error.detail : "No se pudo archivar la imagen");
    }

    return res.json();
}

export async function uploadTapImage(beerId, file, token = localStorage.getItem("token")) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`/api/admin/beers/${beerId}/upload-image`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
    });
    if (res.status === 401) {
        localStorage.removeItem("token");
        window.location.href = "/login";
        throw new Error("Sesión expirada. Inicia sesión de nuevo.");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "No se pudo publicar la imagen");
    }
    if (!data.operational_updated || !data.historical_archived) {
        throw new Error("No se confirmó la publicación en ambos destinos. Revisa el estado antes de continuar.");
    }
    return data;
}

export function tapUploadMessage(data) {
    return `Imagen operativa actualizada. ${data.historical_created
        ? "Obra histórica archivada."
        : "Obra histórica ya archivada; sin duplicados."}`;
}
