import { useRef, useEffect, useState } from "react";

export default function BeerCover({ beer, onClick }) {

    const ref = useRef(null);
    const [styleState, setStyleState] = useState({});

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
        let frame;

        const update = () => {
            if (!ref.current) return;

            const rect = ref.current.getBoundingClientRect();
            const centerX = window.innerWidth / 2;
            const elementCenter = rect.left + rect.width / 2;

            const distance = elementCenter - centerX;
            const normalized = distance / centerX;

            // 🔥 3D
            const intensity = Math.min(Math.abs(normalized), 1);

            const scale = 1 - intensity * 0.35;
            const rotate = normalized * 50;
            const translateZ = -intensity * 120;

            const opacity = 1 - Math.min(Math.abs(normalized) * 0.6, 0.6);
            const zIndex = 1000 - Math.abs(Math.round(normalized * 1000));

            // 🔥 SHADING (tu versión actual)
            let shading = 0;

            if (normalized > 0.35) shading = 0.20;
            else if (normalized > 0.1) shading = 0.10;
            else if (normalized < -0.35) shading = -0.20;
            else if (normalized < -0.1) shading = -0.10;

            // 🔥 BLUR CUANTIZADO (NUEVO)
            let blur = 0;

            if (Math.abs(normalized) > 0.4) blur = 2;
            else if (Math.abs(normalized) > 0.2) blur = 1;

            setStyleState({
                transform: `
                    perspective(1000px)
                    translateZ(${translateZ}px)
                    scale(${scale})
                    rotateY(${rotate}deg)
                `,
                opacity,
                zIndex,
                shading,
                blur,
            });

            frame = requestAnimationFrame(update);
        };

        update();

        return () => cancelAnimationFrame(frame);
    }, []);

    const getImageSrc = () => {
        if (!beer.image_url) return "";
        return beer.image_url;
    };

    return (
        <div
            ref={ref}
            onClick={(e) => {
                e.stopPropagation();

                if (!ref.current) return;

                const container = ref.current.parentElement;

                const rect = ref.current.getBoundingClientRect();
                const centerX = window.innerWidth / 2;
                const elementCenter = rect.left + rect.width / 2;

                const distance = elementCenter - centerX;

                if (Math.abs(distance) > 10) {
                    const scrollLeft =
                        ref.current.offsetLeft -
                        container.offsetWidth / 2 +
                        ref.current.offsetWidth / 2;

                    container.scrollTo({
                        left: scrollLeft,
                        behavior: "smooth",
                    });

                    return;
                }

                onClick && onClick();
            }}
            style={{
                width: isLandscape ? "200px" : "min(60vw, 260px)",
                height: isLandscape ? "300px" : "min(90vw, 390px)",

                borderRadius: "14px",
                overflow: "hidden",
                position: "relative",
                background: "#111",
                boxShadow: "0 10px 25px rgba(0,0,0,0.6)",
                flexShrink: 0,
                cursor: "pointer",
                scrollSnapAlign: "center",
                transformOrigin: "center center",
                ...styleState,
                transition: "transform 0.25s ease, opacity 0.25s ease",
            }}
        >
            {beer.image_url && (
                <img
                    key={beer.image_url}
                    src={getImageSrc()}
                    alt={beer.name}
                    style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",

                        // 🔥 BLUR APLICADO
                        filter: `blur(${styleState.blur || 0}px)`,
                    }}
                />
            )}

            {/* 🔥 SHADING */}
            <div
                style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: "100%",
                    pointerEvents: "none",
                    background: `linear-gradient(
                        to right,
                        rgba(0,0,0,${Math.max(0, styleState.shading || 0)}),
                        rgba(0,0,0,0),
                        rgba(0,0,0,${Math.max(0, -(styleState.shading || 0))})
                    )`,
                }}
            />

            <div
                style={{
                    position: "absolute",
                    bottom: 0,
                    width: "100%",
                    padding: "10px",
                    background: "linear-gradient(transparent, rgba(0,0,0,0.8))",
                    color: "#fff",
                    fontSize: "13px",
                }}
            >
                <strong>{beer.name}</strong>
            </div>
        </div>
    );
}