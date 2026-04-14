import { Link, Outlet, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";

export default function AdminLayout() {

    const navigate = useNavigate();
    const [menuOpen, setMenuOpen] = useState(false);
    const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

    // 🔥 detectar tamaño de pantalla (reactivo)
    useEffect(() => {
        const handleResize = () => {
            setIsMobile(window.innerWidth < 768);
        };

        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    // 🔥 cerrar menú automáticamente en desktop
    useEffect(() => {
        if (!isMobile) {
            setMenuOpen(false);
        }
    }, [isMobile]);

    const handleLogout = () => {
        localStorage.removeItem("token");
        navigate("/login");
    };

    return (
        <div style={{
            height: "100vh",
            width: "100vw",
            display: "flex",
            flexDirection: "column",
            background: "#0b0b0b",
            color: "white"
        }}>

            {/* 🔥 HEADER */}
            <div style={{
                height: "70px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 20px",
                borderBottom: "1px solid #444"
            }}>

                {isMobile && (
                    <button onClick={() => setMenuOpen(true)}>☰</button>
                )}

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
                    width: "140px",
                    borderRight: "1px solid #444",
                    padding: "20px",
                    background: "#111",

                    position: isMobile ? "fixed" : "relative",
                    left: isMobile ? (menuOpen ? "0" : "-240px") : "0",
                    top: isMobile ? "70px" : "0",
                    height: isMobile ? "calc(100vh - 70px)" : "100%",
                    transition: "left 0.3s",
                    zIndex: 1000
                }}>
                    <p>
                        <Link to="/admin/beers" onClick={() => setMenuOpen(false)}>
                            Beers
                        </Link>
                    </p>

                    <p>
                        <Link to="/admin/parser" onClick={() => setMenuOpen(false)}>
                            Parser
                        </Link>
                    </p>

                    <p>
                        <Link to="/admin/stats" onClick={() => setMenuOpen(false)}>
                            Stats
                        </Link>
                    </p>
                </div>

                {/* 🔥 OVERLAY */}
                {isMobile && menuOpen && (
                    <div
                        onClick={() => setMenuOpen(false)}
                        style={{
                            position: "fixed",
                            top: "70px",
                            left: 0,
                            width: "100%",
                            height: "calc(100vh - 70px)",
                            background: "rgba(0,0,0,0.5)",
                            zIndex: 999
                        }}
                    />
                )}

                {/* 🔥 CONTENIDO */}
                <div style={{
                    flex: 1,
                    padding: "20px",
                    overflowY: "auto",
                }}>
                    <Outlet />
                </div>

            </div>

        </div>
    );
}