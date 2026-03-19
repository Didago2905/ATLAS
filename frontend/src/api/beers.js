const API_URL = "http://localhost:8001";

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

export async function fetchBeers() {
    const res = await fetch(`${API_URL}/beers`);

    if (!res.ok) throw new Error("Error fetching beers");

    return res.json();
}

// =========================
// ADMIN
// =========================

export async function fetchAdminBeers() {
    const res = await fetch(`${API_URL}/admin/beers`, {
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

// (opcional, ya casi no necesario)
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
    const res = await fetch("http://localhost:8001/admin/login", {
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