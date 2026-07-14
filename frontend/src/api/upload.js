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
        return;
    }

    if (!res.ok) {
        throw new Error("Upload failed");
    }

    return res.json();
}