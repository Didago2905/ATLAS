import { useParams, useNavigate } from "react-router-dom";
import useTapBeers from "../hooks/useTapBeers";
import BeerCard from "../components/BeerCard";
import { useState, useEffect, useRef } from "react";

export default function BeerDetail() {
    const { id } = useParams();
    const beers = useTapBeers();
    const navigate = useNavigate();

    const beer = beers.find((b) => String(b.id) === id);
    const index = beers.findIndex((b) => String(b.id) === id);

    const prevBeer = beers[index - 1];
    const nextBeer = beers[index + 1];

    const [visible, setVisible] = useState(false);
    const [direction, setDirection] = useState(null);
    const [animating, setAnimating] = useState(false);

    const startX = useRef(0);

    const isMobile = window.innerWidth < 768;

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
                alignItems: "flex-start", // 🔥 importante
                position: "relative",
                overflowY: "auto",
                paddingTop: "60px",
                paddingBottom: "40px"
            }}
        >
            {/* 🔙 BACK */}
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
                }}
                onTouchEnd={(e) => {
                    const endX = e.changedTouches[0].clientX;
                    const delta = endX - startX.current;

                    if (delta > 50 && prevBeer) {
                        setDirection("right");
                        setAnimating(true);

                        setTimeout(() => {
                            navigate(`/beer/${prevBeer.id}`, { replace: true });
                        }, 120);
                    }

                    if (delta < -50 && nextBeer) {
                        setDirection("left");
                        setAnimating(true);

                        setTimeout(() => {
                            navigate(`/beer/${nextBeer.id}`, { replace: true });
                        }, 120);
                    }
                }}
            >

                {/* FLECHAS SOLO PC */}
                {!isMobile && prevBeer && (
                    <div
                        onClick={() =>
                            navigate(`/beer/${prevBeer.id}`, { replace: true })
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
                            navigate(`/beer/${nextBeer.id}`, { replace: true })
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
                    }}
                >
                    <div
                        style={{
                            width: "100%",
                            height: "100%",

                            opacity: animating ? 0.6 : (visible ? 1 : 0.2),

                            transform: animating
                                ? direction === "left"
                                    ? "translateX(-20px) scale(0.96)"
                                    : "translateX(20px) scale(0.96)"
                                : visible
                                    ? "translateY(0px) scale(1)"
                                    : "translateY(30px) scale(0.92)",

                            transition: animating
                                ? "all 0.12s ease"
                                : "all 0.45s cubic-bezier(0.22, 1, 0.36, 1)",
                        }}
                    >
                        <BeerCard beer={beer} />
                    </div>
                </div>

            </div>
        </div>
    );
}