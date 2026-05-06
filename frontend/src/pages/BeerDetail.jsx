import { useParams, useNavigate } from "react-router-dom";
import useTapBeers from "../hooks/useTapBeers";
import BeerCard from "../components/BeerCard";
import { useState, useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

export default function BeerDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const location = useLocation();

    const beersFromState = location.state?.beers;
    const indexFromState = location.state?.currentIndex;

    const [stableBeers, setStableBeers] = useState(null);

    const fallbackBeers = useTapBeers();
    const beers = stableBeers || fallbackBeers;

    const beer = beers.find((b) => String(b.id) === id);

    const index =
        indexFromState !== undefined
            ? indexFromState
            : beers.findIndex((b) => String(b.id) === id);

    const prevBeer = beers[index - 1];
    const nextBeer = beers[index + 1];

    const [visible, setVisible] = useState(false);
    const [direction, setDirection] = useState(null);
    const [animating, setAnimating] = useState(false);

    const [viewMode, setViewMode] = useState("info");

    const startX = useRef(0);
    const pressTimer = useRef(null);

    const isMobile = window.innerWidth < 768;

    useEffect(() => {
        if (beersFromState && !stableBeers) {
            setStableBeers(beersFromState);
        }
    }, [beersFromState]);

    useEffect(() => {
        setVisible(true);
    }, []);

    useEffect(() => {
        setAnimating(false);
        setDirection(null);
    }, [id]);

    if (!beers.length) {
        return <div style={{ height: "100vh", background: "#000" }} />;
    }

    if (!beer) {
        return <div style={{ height: "100vh", background: "#000" }} />;
    }

    return (
        <div
            style={{
                minHeight: "100vh",
                background: "#000",
                display: "flex",
                justifyContent: "center",
                alignItems: "flex-start",
                position: "relative",
                overflowY: "auto",
                paddingTop: "60px",
                paddingBottom: "40px"
            }}
        >
            {/* BACK */}
            <div
                style={{
                    position: "absolute",
                    top: "20px",
                    left: "50%",
                    transform: "translateX(-50%)",
                    width: "100%",
                    maxWidth: "360px",
                    zIndex: 10,
                }}
            >
                <div
                    onClick={() => navigate("/", { replace: true })}
                    style={{
                        color: "#aaa",
                        cursor: "pointer",
                        fontSize: "16px",
                        opacity: 0.7,
                    }}
                >
                    ← volver
                </div>
            </div>

            {/* WRAPPER */}
            <div
                style={{
                    position: "relative",
                    width: "100%",
                    maxWidth: "600px",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                }}
                onTouchStart={(e) => {
                    startX.current = e.touches[0].clientX;

                    pressTimer.current = setTimeout(() => {
                        setViewMode((prev) =>
                            prev === "info" ? "art" : "info"
                        );
                    }, 450);
                }}
                onTouchEnd={(e) => {
                    clearTimeout(pressTimer.current);

                    const endX = e.changedTouches[0].clientX;
                    const delta = endX - startX.current;

                    if (delta > 50 && prevBeer) {
                        setDirection("right");
                        setAnimating(true);

                        setTimeout(() => {
                            navigate(`/beer/${prevBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index - 1
                                }
                            });
                        }, 120);
                    }

                    if (delta < -50 && nextBeer) {
                        setDirection("left");
                        setAnimating(true);

                        setTimeout(() => {
                            navigate(`/beer/${nextBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index + 1
                                }
                            });
                        }, 120);
                    }
                }}
            >

                {/* FLECHAS */}
                {!isMobile && prevBeer && (
                    <div
                        onClick={() =>
                            navigate(`/beer/${prevBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index - 1
                                }
                            })
                        }
                        style={{
                            position: "absolute",
                            left: 0,
                            top: "50%",
                            transform: "translateY(-50%)",
                            fontSize: "32px",
                            opacity: 0.5,
                            cursor: "pointer",
                        }}
                    >
                        ←
                    </div>
                )}

                {!isMobile && nextBeer && (
                    <div
                        onClick={() =>
                            navigate(`/beer/${nextBeer.id}`, {
                                replace: true,
                                state: {
                                    beers,
                                    currentIndex: index + 1
                                }
                            })
                        }
                        style={{
                            position: "absolute",
                            right: 0,
                            top: "50%",
                            transform: "translateY(-50%)",
                            fontSize: "32px",
                            opacity: 0.5,
                            cursor: "pointer",
                        }}
                    >
                        →
                    </div>
                )}

                {/* CARD */}
                <div
                    style={{
                        width: "100%",
                        maxWidth: "360px",
                        display: "flex",
                        justifyContent: "center",

                        contain: "layout paint", // 🔥 PASO 2
                    }}
                >
                    <div
                        style={{
                            width: "100%",

                            opacity: animating ? 0.6 : (visible ? 1 : 0.2),

                            transform: (
                                animating
                                    ? direction === "left"
                                        ? "translateX(-20px) scale(0.96)"
                                        : "translateX(20px) scale(0.96)"
                                    : visible
                                        ? "translateY(0px) scale(1)"
                                        : "translateY(30px) scale(0.92)"
                            ) + " translateZ(0)", // 🔥 PASO 1

                            willChange: "transform", // 🔥 PASO 1

                            transition: animating
                                ? "all 0.12s ease"
                                : "all 0.45s cubic-bezier(0.22, 1, 0.36, 1)",
                        }}
                    >
                        <div style={{ position: "relative", width: "100%" }}>

                            {/* INFO */}
                            <div
                                style={{
                                    opacity: viewMode === "info" ? 1 : 0,
                                    transform: viewMode === "info" ? "scale(1)" : "scale(0.96)",
                                    transition: "all 0.25s ease",
                                }}
                            >
                                <BeerCard beer={beer} />
                            </div>

                            {/* ARTE */}
                            {viewMode === "art" && (
                                <div
                                    style={{
                                        position: "absolute",
                                        top: 0,
                                        left: 0,
                                        right: 0,
                                        bottom: 0,
                                        display: "flex",
                                        justifyContent: "center",
                                        alignItems: "center",
                                        background: "#000",
                                        opacity: 1,
                                        transition: "opacity 0.25s ease",
                                    }}
                                >
                                    <img
                                        src={beer.image_url}
                                        draggable={false}
                                        onContextMenu={(e) => e.preventDefault()}
                                        style={{
                                            width: "100%",
                                            height: "100%",
                                            objectFit: "contain",
                                            userSelect: "none",
                                            WebkitUserSelect: "none",
                                            WebkitTouchCallout: "none",
                                            pointerEvents: "auto",
                                        }}
                                    />
                                </div>
                            )}

                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
}