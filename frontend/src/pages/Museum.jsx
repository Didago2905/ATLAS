import { useState, useEffect, useRef } from "react";
import useTapBeers from "../hooks/useTapBeers";
import BeerCoverV2 from "../components/BeerCoverV2";

export default function Museum() {
    const beers = useTapBeers();

    const [mode, setMode] = useState("fichas");
    const [museumData, setMuseumData] = useState([]);
    const [activeItem, setActiveItem] = useState(null);

    const [showUI, setShowUI] = useState(true);

    const containerRef = useRef(null);

    // 🔥 scroll state
    const [scrollLeft, setScrollLeft] = useState(0);
    const [containerWidth, setContainerWidth] = useState(0);

    const [isLandscape, setIsLandscape] = useState(
        window.innerWidth > window.innerHeight
    );

    useEffect(() => {
        const handleResize = () => {
            setIsLandscape(window.innerWidth > window.innerHeight);
        };

        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    useEffect(() => {
        fetch("/api/public/museum")
            .then(res => res.json())
            .then(data => setMuseumData(data))
            .catch(err => console.error("Museum fetch error:", err));
    }, []);

    // 🔥 FIX REAL AQUÍ
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        // 🔥 FORZAR INICIAL (CLAVE)
        const init = () => {
            const width = container.offsetWidth;
            if (width !== 0) {
                setContainerWidth(width);
            }
        };

        init(); // 🔥 primer intento inmediato

        // 🔥 segundo intento (cuando layout ya está listo)
        requestAnimationFrame(init);

        const handleScroll = () => {
            setScrollLeft(container.scrollLeft);
        };

        const handleResize = () => {
            const width = container.offsetWidth;
            if (width !== 0) {
                setContainerWidth(width);
            }
        };

        container.addEventListener("scroll", handleScroll, { passive: true });
        window.addEventListener("resize", handleResize);

        return () => {
            container.removeEventListener("scroll", handleScroll);
            window.removeEventListener("resize", handleResize);
        };
    }, []);

    // 🔥 fade UI (igual)
    useEffect(() => {
        let timeout;

        const hideUI = () => {
            setShowUI(false);

            clearTimeout(timeout);
            timeout = setTimeout(() => {
                setShowUI(true);
            }, 450);
        };

        window.addEventListener("scroll", hideUI, { passive: true });
        window.addEventListener("touchmove", hideUI, { passive: true });

        return () => {
            window.removeEventListener("scroll", hideUI);
            window.removeEventListener("touchmove", hideUI);
        };
    }, []);

    let data = [];

    if (mode === "fichas") {
        data = museumData.filter(item => item.type === "fichas/antiguas");
    }

    if (mode === "tap") {
        data = beers;
    }

    if (!data.length) {
        return <div style={{ height: "100vh", background: "#000" }} />;
    }

    return (
        <>
            <div
                ref={containerRef}
                style={{
                    height: "100vh",
                    background: "#000",
                    display: "flex",
                    alignItems: "center",
                    overflowX: "auto",
                    gap: isLandscape ? "40px" : "28px",
                    padding: isLandscape ? "0 10px 0 80px" : "0 10px",
                    scrollSnapType: "x proximity",
                    scrollBehavior: "smooth",
                    position: "relative",
                }}
            >

                {/* SELECTOR */}
                <div
                    style={{
                        position: "fixed",
                        top: isLandscape ? "50%" : "20px",
                        left: isLandscape ? "20px" : "50%",
                        transform: isLandscape
                            ? "translateY(-50%) translateZ(0)"
                            : "translateX(-50%) translateZ(0)",
                        display: "flex",
                        flexDirection: isLandscape ? "column" : "row",
                        gap: "10px",
                        zIndex: 99999,
                        backdropFilter: "blur(8px)",
                        background: "rgba(0,0,0,0.4)",
                        padding: "8px",
                        borderRadius: "12px",
                        opacity: showUI ? 1 : 0,
                        pointerEvents: showUI ? "auto" : "none",
                        transition: "opacity 0.25s ease",
                    }}
                >
                    <button
                        onClick={() => setMode("fichas")}
                        style={{
                            padding: "10px",
                            borderRadius: "50%",
                            border: "1px solid #333",
                            background: mode === "fichas" ? "#fff" : "#111",
                            color: mode === "fichas" ? "#000" : "#fff",
                            cursor: "pointer",
                            width: "44px",
                            height: "44px",
                        }}
                    >
                        ▭
                    </button>

                    <button
                        onClick={() => setMode("tap")}
                        style={{
                            padding: "10px",
                            borderRadius: "50%",
                            border: "1px solid #333",
                            background: mode === "tap" ? "#fff" : "#111",
                            color: mode === "tap" ? "#000" : "#fff",
                            cursor: "pointer",
                            width: "44px",
                            height: "44px",
                        }}
                    >
                        ▦
                    </button>
                </div>

                <>
                    <div
                        style={{
                            minWidth: isLandscape
                                ? "calc(50vw - 120px)"
                                : "calc(50vw - 150px)"
                        }}
                    />

                    {data.map((item) => (
                        <BeerCoverV2
                            key={item.id}
                            beer={item}
                            scrollLeft={scrollLeft}
                            containerWidth={containerWidth}
                            onClick={() => setActiveItem(item)}
                        />
                    ))}

                    <div
                        style={{
                            minWidth: isLandscape
                                ? "calc(50vw - 100px)"
                                : "calc(50vw - 130px)"
                        }}
                    />
                </>
            </div>

            {activeItem && (
                <div
                    onClick={() => setActiveItem(null)}
                    style={{
                        position: "fixed",
                        top: 0,
                        left: 0,
                        width: "100vw",
                        height: "100vh",
                        background: "rgba(0,0,0,0.97)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        zIndex: 9999,
                        cursor: "pointer",
                    }}
                >
                    <img
                        src={activeItem.image_url}
                        style={{
                            maxWidth: "95%",
                            maxHeight: "95%",
                            objectFit: "contain",
                        }}
                    />
                </div>
            )}
        </>
    );
}