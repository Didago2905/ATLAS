import { Link, Outlet, useNavigate } from "react-router-dom";

export default function AdminLayout() {

    const navigate = useNavigate();

    const handleLogout = () => {
        localStorage.removeItem("token");
        navigate("/login");
    };

    return (
        <div style={{
            height: "100vh",
            width: "100vw", // 🔥 CLAVE
            display: "flex",
            flexDirection: "column",
            background: "#0b0b0b",
            color: "white"
        }}>

            {/* 🔥 HEADER */}
            <div style={{
                height: "70px",
                width: "100%", // 🔥 CLAVE
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 20px",
                borderBottom: "1px solid #444",
                boxSizing: "border-box"
            }}>
                <h2 style={{ margin: 0 }}>Admin Panel</h2>

                <button
                    onClick={handleLogout}
                    style={{
                        padding: "8px 16px",
                        background: "#1a1a1a",
                        border: "1px solid #333",
                        color: "white",
                        borderRadius: "6px",
                        cursor: "pointer"
                    }}
                >
                    Logout
                </button>
            </div>

            {/* 🔥 BODY */}
            <div style={{
                display: "flex",
                flex: 1,
                width: "100%",
                overflow: "hidden"
            }}>

                {/* 🔥 SIDEBAR */}
                <div style={{
                    width: "220px",
                    borderRight: "1px solid #444",
                    padding: "20px",
                    boxSizing: "border-box"
                }}>
                    <p><Link to="/admin/beers">Beers</Link></p>
                    <p><Link to="/admin/parser">Parser</Link></p>
                    <p><Link to="/admin/stats">Stats</Link></p>
                </div>

                {/* 🔥 CONTENIDO */}
                <div style={{
                    flex: 1,
                    width: "100%", // 🔥 CLAVE
                    padding: "20px",
                    overflowY: "auto",
                    boxSizing: "border-box"
                }}>
                    <Outlet />
                </div>

            </div>

        </div>
    );
}