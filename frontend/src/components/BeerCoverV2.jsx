import { useRef, useEffect } from "react";

export default function BeerCoverV2({ beer, onClick }) {

    const ref = useRef(null);

    const imgRef = useRef(null);
    const highlightRef = useRef(null);

    useEffect(() => {
        let frame;

        let lastRotate = 0;
        let lastScale = 0;
        let lastZ = 0;

        const update = () => {
            if (!ref.current) return;

            const rect = ref.current.getBoundingClientRect();
            const center =
                (window.visualViewport?.width ??
                    window.innerWidth) / 2;
            const elementCenter = rect.left + rect.width / 2;

            const distance = elementCenter - center;
            const normalized = distance / center;

            const intensity = Math.min(Math.abs(normalized), 1);

            // 🔥 ROTACIÓN LIMPIA
            let rotate = Math.round(normalized * 40);

            if (Math.abs(normalized) < 0.03) {
                rotate = 0;
            } else {
                rotate = Math.round(rotate / 2) * 2;
            }

            // 🔥 ESCALA
            let scale = 1 - intensity * 0.24;
            scale = Math.round(scale * 1000) / 1000;

            // 🔥 PROFUNDIDAD
            const translateZ =
                Math.round((-intensity * 60) / 10) * 10;

            const opacity = 1 - Math.min(intensity * 0.5, 0.5);

            // 🔥 BLUR ESTABLE
            let blur = 0;
            if (intensity > 0.6) blur = 1;
            else if (intensity > 0.35) blur = 0.5;

            // 🔥 HIGHLIGHT (nuevo)
            const highlightStrength = 1 - intensity;
            const highlightOpacity =
                Math.round((highlightStrength * 0.20) * 100) / 100;

            let shading = 0;

            if (normalized > 0.35) shading = 0.20;
            else if (normalized > 0.1) shading = 0.10;
            else if (normalized < -0.35) shading = -0.20;
            else if (normalized < -0.1) shading = -0.10;

            // 🔥 ANTI-JITTER
            const changed =
                Math.abs(rotate - lastRotate) > 0.5 ||
                Math.abs(scale - lastScale) > 0.002 ||
                Math.abs(translateZ - lastZ) > 1;

            if (changed) {
                ref.current.style.transform = `
                    perspective(900px)
                    translateZ(${translateZ}px)
                    rotateY(${rotate}deg)
                    scale(${scale})
                `;

                lastRotate = rotate;
                lastScale = scale;
                lastZ = translateZ;
            }

            ref.current.style.opacity = opacity;

            // 🔥 blur directo
            if (imgRef.current) {
                imgRef.current.style.filter = `blur(${blur}px)`;
            }

            // 🔥 highlight directo
            if (highlightRef.current) {
                highlightRef.current.style.opacity = highlightOpacity;
            }

            frame = requestAnimationFrame(update);
        };

        update();

        return () => cancelAnimationFrame(frame);
    }, []);

    return (
        <div
            ref={ref}
            onClick={(e) => {
                e.stopPropagation();

                if (!ref.current) return;

                const container = ref.current.parentElement;

                const elementCenter =
                    ref.current.offsetLeft +
                    ref.current.offsetWidth / 2;

                const centerX =
                    container.scrollLeft +
                    container.offsetWidth / 2;

                const distance = elementCenter - centerX;

                if (Math.abs(distance) > 10) {
                    const scrollTo =
                        ref.current.offsetLeft -
                        container.offsetWidth / 2 +
                        ref.current.offsetWidth / 2;

                    container.scrollTo({
                        left: scrollTo,
                        behavior: "smooth",
                    });

                    return;
                }

                onClick && onClick();
            }}
            style={{
                width: "220px",
                minWidth: "220px",
                height: "300px",
                margin: "0 12px",

                scrollSnapAlign: "center",

                transformOrigin: "center center",
                backfaceVisibility: "hidden",
                willChange: "transform",

                borderRadius: "14px",
                overflow: "hidden",

                boxShadow: "0 12px 28px rgba(0,0,0,0.55)",

                transition: "opacity 0.2s ease",
            }}
        >
            <div
                style={{
                    width: "100%",
                    height: "100%",
                    borderRadius: "14px",
                    overflow: "hidden",
                    background: "#000",
                    position: "relative",

                    transform: "translateZ(0)",
                    willChange: "auto",
                }}
            >
                {beer?.image_url && (
                    <img
                        ref={imgRef}
                        src={beer.image_url}
                        alt={beer.name}
                        draggable={false}
                        style={{
                            width: "100%",
                            height: "100%",
                            objectFit: "cover",
                            objectPosition: "center 20%",

                            filter: "blur(0px)",

                            transform: "translateZ(0)",
                            willChange: "transform",
                            backfaceVisibility: "hidden",

                            userSelect: "none",
                            WebkitUserSelect: "none",
                            WebkitTouchCallout: "none",
                        }}
                    />
                )}

                {/* 🔥 SHADING */}
                <div
                    style={{
                        position: "absolute",
                        inset: 0,
                        pointerEvents: "none",
                        transform: "translateZ(0)",
                        backfaceVisibility: "hidden",
                        background: `
                            linear-gradient(
                                to right,
                                rgba(0,0,0,0.08),
                                trasnsparent,
                                rgba(0,0,0,0.08)
                            )
                        `,
                    }}
                />

                {/* 🔥 HIGHLIGHT */}
                <div
                    ref={highlightRef}
                    className="highlight"
                    style={{
                        position: "absolute",
                        inset: 0,
                        pointerEvents: "none",
                        opacity: 0,

                        transform: "translateZ(0)",
                        backfaceVisibility: "hidden",

                        background: `
                            radial-gradient(
                                circle at 50% 35%,
                                rgba(255,255,255,0.15),
                                transparent 60%
                            )
                        `,
                    }}
                />
            </div>
        </div>
    );
}