import { useRef, useEffect } from "react";
import { createAnimation } from "../museum/animation";
import { resolveArtworkNavigation } from "../museum/navigation";
import { scrollStageTo } from "../museum/runtime";

export default function BeerCoverV2({ beer, onClick, stageRef, visualScale = 1, frame = { width: 220, height: 300 }, onImageDimensions }) {

    const layoutRef = useRef(null);
    const visualRef = useRef(null);

    const imgRef = useRef(null);
    const highlightRef = useRef(null);

    useEffect(() => {
        let frame = null;
        let active = false;
        let disposed = false;

        const animation = createAnimation({ baseScale: visualScale });

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

        };

        const tick = () => {
            frame = null;
            if (!active || disposed) return;
            update();
            frame = requestAnimationFrame(tick);
        };

        const setActive = next => {
            if (disposed || next === active) return;
            active = next;
            if (active) {
                // Refresh frozen transforms immediately, before an incoming card is visible.
                update();
                frame = requestAnimationFrame(tick);
            } else if (frame !== null) {
                cancelAnimationFrame(frame);
                frame = null;
            }
        };

        const stage = stageRef.current;
        const slot = layoutRef.current;
        if (!stage || !slot) return;
        // Observe the stable layout slot, not the animated visual. One viewport of
        // overscan on each side lets returning cards settle before entering the stage.
        const observer = new IntersectionObserver(entries => {
            for (const entry of entries) setActive(entry.isIntersecting);
        }, { root: stage, rootMargin: "0px 100% 0px 100%", threshold: 0 });
        const bounds = stage.getBoundingClientRect();
        const rect = slot.getBoundingClientRect();
        setActive(rect.right >= bounds.left - bounds.width && rect.left <= bounds.right + bounds.width
            && rect.bottom >= bounds.top && rect.top <= bounds.bottom);
        observer.observe(slot);

        return () => {
            disposed = true;
            active = false;
            observer.disconnect();
            if (frame !== null) cancelAnimationFrame(frame);
        };
    }, [visualScale, stageRef]);

    return (
        <div
            ref={layoutRef}
            data-atlas-museum-card
            data-atlas-museum-card-id={beer?.id}
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

                    window.__ATLAS_MUSEUM_MOTION_PROBE__
                        ?.markNavigationCenterRequest({
                            cardId: beer?.id ?? null,
                            targetLeft: scrollTo,
                            layoutCenterDelta: elementCenter - centerX,
                        });

                    scrollStageTo(container, scrollTo);

                    return;
                }

                onClick && onClick();
            }}
            style={{
                width: `${frame.width}px`,
                minWidth: 0,
                height: `${frame.height}px`,
                flex: `0 0 ${frame.width}px`,

                scrollSnapAlign: "center",
            }}
        >
            <div
                ref={visualRef}
                data-atlas-museum-visual
                data-atlas-museum-visual-scale={visualScale}
                style={{
                    width: "calc(100% - 16px)",
                    height: "calc(100% - 16px)",
                    margin: "8px",
                    borderRadius: 0,
                    overflow: "visible",
                    background: "transparent",
                    position: "relative",
                    boxSizing: "border-box",
                    padding: 0,

                    transform: "translateZ(0)",
                    transformOrigin: "center center",
                    backfaceVisibility: "hidden",
                    willChange: "transform",
                    boxShadow: "none",
                    transition: "opacity 0.2s ease",
                }}
            >
                {beer?.image_url && (
                    <img
                        ref={imgRef}
                        src={beer.image_url}
                        alt={beer.name}
                        draggable={false}
                        onLoad={event => onImageDimensions?.(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)}
                        style={{
                            width: "100%",
                            height: "100%",
                            display: "block",
                            objectFit: "contain",
                            objectPosition: "center",

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
