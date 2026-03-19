import { useState } from "react";
import { adminLogin } from "../api/beers";

export default function AdminLogin({ onLogin }) {

    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();

        try {
            setLoading(true);

            const data = await adminLogin(password);

            localStorage.setItem("token", data.access_token);

            onLogin();

        } catch {
            alert("Incorrect password");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            background: "#0b0b0b",
            color: "white"
        }}>

            <form
                onSubmit={handleSubmit}
                style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "15px",
                    width: "320px"
                }}
            >

                <h2 style={{
                    textAlign: "center",
                    fontSize: "28px"
                }}>
                    Admin Login
                </h2>

                <input
                    type="password"
                    placeholder="Enter password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{
                        padding: "12px",
                        borderRadius: "6px",
                        border: "1px solid #333",
                        background: "#111",
                        color: "white",
                        fontSize: "16px"
                    }}
                />

                <button
                    type="submit"
                    disabled={loading}
                    style={{
                        padding: "12px",
                        borderRadius: "6px",
                        background: "#1a1a1a",
                        border: "1px solid #333",
                        color: "white",
                        cursor: "pointer",
                        fontSize: "16px"
                    }}
                >
                    {loading ? "Logging in..." : "Login"}
                </button>

            </form>

        </div>
    );
}