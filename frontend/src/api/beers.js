const API_URL = import.meta.env.VITE_API_URL;

// 🔐 Helper para headers con token automático
const getAuthHeaders = () => {
    const token = localStorage.getItem("token");

    return {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`
    };
};

// =========================
// PUBLIC
// =========================

export async function fetchPublicBeers() {
    const res = await fetch(`${API_URL}/public/beers?limit=100`)
    if (!res.ok) throw new Error("Error fetching public beers");

    return res.json();
}

// =========================
// ADMIN
// =========================

export async function fetchAdminBeers() {
    const res = await fetch(`${API_URL}/admin/beers?limit=100`, {
        headers: getAuthHeaders()
    });

    if (!res.ok) throw new Error("Error fetching admin beers");

    return res.json();
}

export async function createBeer(data) {
    const res = await fetch(`${API_URL}/admin/beers`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify(data)
    });

    if (!res.ok) throw new Error("Error creating beer");

    return res.json();
}

export async function updateBeer(id, data) {
    const res = await fetch(`${API_URL}/admin/beers/${id}`, {
        method: "PUT",
        headers: getAuthHeaders(),
        body: JSON.stringify(data)
    });

    if (!res.ok) throw new Error("Error updating beer");

    return res.json();
}

export async function toggleTap(id, value) {
    const res = await fetch(`${API_URL}/admin/beers/${id}`, {
        method: "PUT",
        headers: getAuthHeaders(),
        body: JSON.stringify({ is_available: value })
    });

    if (!res.ok) throw new Error("Error toggling beer");

    return res.json();
}

export async function adminLogin(password) {
    const res = await fetch(`${API_URL}/admin/login`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ password })
    });

    if (!res.ok) {
        throw new Error("Invalid credentials");
    }

    return res.json();
}