import { useRef, useEffect } from "react";
import { createAnimation } from "../museum/animation";
import { resolveArtworkNavigation } from "../museum/navigation";
import { scrollStageTo } from "../museum/runtime";

export default function BeerCoverV2({ beer, onClick, stageRef }) {

    const layoutRef = useRef(null);
    const visualRef = useRef(null);

    const imgRef = useRef(null);
    const highlightRef = useRef(null);

    useEffect(() => {
        let frame;

        const animation = createAnimation();

        const update = () => {
            if (!visualRef.current) return;

            const rect = visualRef.current.getBoundingClientRect();
            const center =
                (window.visualViewport?.width ??
                    window.innerWidth) / 2;
            const elementCenter = rect.left + rect.width / 2;

            animation.update({
                cardCenterX: elementCenter,
                viewportCenterX: center,
                card: visualRef.current,
                image: imgRef.current,
                highlight: highlightRef.current,
            });

            frame = requestAnimationFrame(update);
        };

        update();

        return () => cancelAnimationFrame(frame);
    }, []);

    return (
        <div
            ref={layoutRef}
            onClick={(e) => {
                e.stopPropagation();

                if (!layoutRef.current || !stageRef?.current) return;

                const container = stageRef.current;

                const elementCenter =
                    layoutRef.current.offsetLeft +
                    layoutRef.current.offsetWidth / 2;

                const centerX =
                    container.scrollLeft +
                    container.offsetWidth / 2;

                const navigation = resolveArtworkNavigation(
                    elementCenter,
                    centerX
                );

                if (navigation === "center") {
                    const scrollTo =
                        layoutRef.current.offsetLeft -
                        container.offsetWidth / 2 +
                        layoutRef.current.offsetWidth / 2;

                    scrollStageTo(container, scrollTo);

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
            }}
        >
            <div
                ref={visualRef}
                style={{
                    width: "100%",
                    height: "100%",
                    borderRadius: "14px",
                    overflow: "hidden",
                    background: "#000",
                    position: "relative",

                    transform: "translateZ(0)",
                    transformOrigin: "center center",
                    backfaceVisibility: "hidden",
                    willChange: "transform",
                    boxShadow: "0 12px 28px rgba(0,0,0,0.55)",
                    transition: "opacity 0.2s ease",
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
