import { useState, useEffect, useRef } from "react";
import useCatalogSession from "../catalog/useCatalogSession";
import BeerCoverV2 from "../components/BeerCoverV2";
import { createArchive } from "../museum/archive";
import { createExhibition } from "../museum/exhibition";
import { hideControls, showControls } from "../museum/animation";
import { createSelection } from "../museum/selection";
import {
    MUSEUM_MODES,
    selectMuseumMode,
} from "../museum/navigation";
import {
    measureStageWidth,
    readViewportDimensions,
    observeWindowResize,
    observeStageScroll,
} from "../museum/runtime";
import {
    getStageDimensions,
    getViewport,
} from "../museum/viewport";

export default function Museum() {
    console.log("[MUSEUM_QA] Museum component mounted");
    const { beers } = useCatalogSession();
    const museumProbe = window.__ATLAS_MUSEUM_PROBE__ === true;

    const [mode, setMode] = useState(
        MUSEUM_MODES.FICHAS
    );
    const [museumData, setMuseumData] = useState([]);
    const [activeItem, setActiveItem] = useState(null);
    const [probeSnapshot, setProbeSnapshot] = useState(null);

    const selectionRef = useRef(null);

    if (!selectionRef.current) {
        selectionRef.current = createSelection();
    }

    const [showUI, setShowUI] = useState(true);

    const containerRef = useRef(null);

    // 🔥 scroll state
    const [scrollLeft, setScrollLeft] = useState(0);
    const [containerWidth, setContainerWidth] = useState(0);

    const [isLandscape, setIsLandscape] = useState(
        getViewport(readViewportDimensions()).isLandscape
    );

    const toRect = (node) => {
        if (!node) return null;

        const rect = node.getBoundingClientRect();

        return {
            top: Math.round(rect.top),
            left: Math.round(rect.left),
            right: Math.round(rect.right),
            bottom: Math.round(rect.bottom),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
        };
    };

    // 🔥 FIX REAL AQUÍ
    useEffect(() => {

        console.log("[MUSEUM_QA] useEffect entered");

        requestAnimationFrame(() => {
            console.log(
                "[MUSEUM_QA] containerRef after RAF",
                containerRef.current
            );
        });

        const container = containerRef.current;

        if (!container) {
            console.log("[MUSEUM_QA] containerRef is NULL");
            return;
        }

        console.log("[MUSEUM_QA] containerRef OK");

        // 🔥 FORZAR INICIAL (CLAVE)
        const init = () => {
            const width = getStageDimensions(measureStageWidth(container)).width;
            if (width !== 0) {
                setContainerWidth(width);
            }
        };

        init();

        requestAnimationFrame(init);

        const handleScroll = () => {
            setScrollLeft(container.scrollLeft);

            console.log("[MUSEUM_QA][SCROLL]", {
                scrollLeft: container.scrollLeft,
                scrollWidth: container.scrollWidth,
                clientWidth: container.clientWidth,
            });

            logMuseumProbe("museum-scroll");
        };

        const handleResize = () => {
            const width = getStageDimensions(measureStageWidth(container)).width;
            if (width !== 0) {
                setContainerWidth(width);
            }
        };

        console.log("[MUSEUM_QA] Scroll listener attached");

        const stopObservingScroll =
            observeStageScroll(container, handleScroll);
        const stopObservingResize =
            observeWindowResize(handleResize);

        return () => {
            stopObservingScroll();
            stopObservingResize();
        };

    }, []);

    const readMuseumProbeSnapshot = (phase) => {
        const container = containerRef.current;
        const activeCard = getActiveCardNode();
        const activeRect = activeCard?.getBoundingClientRect();
        const visibleHeight = window.visualViewport?.height || window.innerHeight;
        const stageRect = container?.getBoundingClientRect();
        const centerY = visibleHeight / 2;
        const activeCenterY = activeRect
            ? activeRect.top + activeRect.height / 2
            : null;

        return {
            phase,
            timestamp: Math.round(performance.now()),
            mode,
            orientation: isLandscape ? "landscape" : "portrait",
            viewport: {
                innerWidth: window.innerWidth,
                innerHeight: window.innerHeight,
                visualViewportHeight: window.visualViewport?.height,
                visualViewportWidth: window.visualViewport?.width,
                visualViewportOffsetTop: window.visualViewport?.offsetTop,
                visualViewportPageTop: window.visualViewport?.pageTop,
                heightDelta: window.visualViewport?.height
                    ? Math.round(window.innerHeight - window.visualViewport.height)
                    : null,
            },
            scroll: {
                windowScrollY: window.scrollY,
                containerScrollLeft: container?.scrollLeft ?? null,
            },
            rects: {
                stage: toRect(container),
                activeCard: toRect(activeCard),
            },
            center: {
                viewportY: Math.round(centerY),
                activeCardY: activeCenterY !== null ? Math.round(activeCenterY) : null,
                deltaY:
                    activeCenterY !== null
                        ? Math.round(activeCenterY - centerY)
                        : null,
            },
            spacing: {
                topDeadZone: activeRect ? Math.round(activeRect.top) : null,
                bottomDeadZone: activeRect
                    ? Math.round(visibleHeight - activeRect.bottom)
                    : null,
                stageTop: stageRect ? Math.round(stageRect.top) : null,
                stageBottom: stageRect ? Math.round(visibleHeight - stageRect.bottom) : null,
            },
            compositing: activeCard
                ? {
                    transform: window.getComputedStyle(activeCard).transform,
                    opacity: window.getComputedStyle(activeCard).opacity,
                    willChange: window.getComputedStyle(activeCard).willChange,
                    filter: window.getComputedStyle(
                        activeCard.querySelector("img") || activeCard
                    ).filter,
                }
                : null,
        };
    };

    const logMuseumProbe = (phase) => {
        if (!museumProbe) return;

        const snapshot = readMuseumProbeSnapshot(phase);
        console.log("[museum-viewport]", {
            phase,
            viewport: snapshot.viewport,
            orientation: snapshot.orientation,
            scroll: snapshot.scroll,
        });
        console.log("[museum-layout]", snapshot);
        console.log("[museum-compositing]", {
            phase,
            activeCard: snapshot.compositing,
        });
        setProbeSnapshot(snapshot);
    };

    useEffect(() => {
        const handleResize = () => {
            setIsLandscape(getViewport(readViewportDimensions()).isLandscape);
        };

        const stopObservingResize =
            observeWindowResize(handleResize);

        return () => {
            stopObservingResize();
        };
    }, []);

    useEffect(() => {
        if (!museumProbe) return;

        logMuseumProbe("mount");

        let secondFrame = null;
        const firstFrame = requestAnimationFrame(() => {
            logMuseumProbe("first-raf");

            secondFrame = requestAnimationFrame(() => {
                logMuseumProbe("second-raf");
            });
        });

        const handleResize = () => logMuseumProbe("window.resize");
        const handleVisualResize = () => logMuseumProbe("visualViewport.resize");
        const handleVisualScroll = () => logMuseumProbe("visualViewport.scroll");
        const handleScroll = () => logMuseumProbe("container.scroll");

        window.addEventListener("resize", handleResize);
        window.visualViewport?.addEventListener("resize", handleVisualResize);
        window.visualViewport?.addEventListener("scroll", handleVisualScroll);
        containerRef.current?.addEventListener("scroll", handleScroll, {
            passive: true,
        });

        return () => {
            cancelAnimationFrame(firstFrame);
            if (secondFrame) {
                cancelAnimationFrame(secondFrame);
            }
            window.removeEventListener("resize", handleResize);
            window.visualViewport?.removeEventListener("resize", handleVisualResize);
            window.visualViewport?.removeEventListener("scroll", handleVisualScroll);
            containerRef.current?.removeEventListener("scroll", handleScroll);
        };
    }, [museumProbe, mode, isLandscape]);

    useEffect(() => {
        fetch("/api/public/museum")
            .then(res => res.json())
            .then(data => setMuseumData(data))
            .catch(err => console.error("Museum fetch error:", err));
    }, []);

    // 🔥 fade UI (igual)
    useEffect(() => {
        let timeout;

        const hideUI = () => {
            hideControls(setShowUI);

            clearTimeout(timeout);
            timeout = setTimeout(() => {
                showControls(setShowUI);
            }, 450);
        };

        window.addEventListener("scroll", hideUI, { passive: true });
        window.addEventListener("touchmove", hideUI, { passive: true });

        return () => {
            window.removeEventListener("scroll", hideUI);
            window.removeEventListener("touchmove", hideUI);
        };
    }, []);

    const artworks = createArchive(museumData);

    const exhibitionArtworks = createExhibition(artworks);

    let data = [];

    if (mode === MUSEUM_MODES.FICHAS) {
        data = exhibitionArtworks.filter(
            item => item.type === "fichas/antiguas"
        );
    }

    if (mode === MUSEUM_MODES.TAP) {
        data = beers;
    }

    const edgeSpacer = isLandscape
        ? "calc(50vw - 120px)"
        : "calc(50vw - 150px)";

    if (!data.length) {
        return <div style={{ height: "100dvh", background: "#000" }} />;
    }

    return (
        <>
            {museumProbe && probeSnapshot && (
                <div
                    style={{
                        position: "fixed",
                        inset: 0,
                        zIndex: 999999,
                        pointerEvents: "none",
                        fontFamily: "monospace",
                        color: "rgba(255,255,255,0.82)",
                    }}
                >
                    <div
                        style={{
                            position: "absolute",
                            top: "50%",
                            left: 0,
                            right: 0,
                            height: "1px",
                            background: "rgba(255,255,255,0.45)",
                        }}
                    />
                    <div
                        style={{
                            position: "absolute",
                            top: 0,
                            bottom: 0,
                            left: "50%",
                            width: "1px",
                            background: "rgba(255,255,255,0.35)",
                        }}
                    />
                    <div
                        style={{
                            position: "absolute",
                            top: "env(safe-area-inset-top)",
                            left: 0,
                            right: 0,
                            height: "1px",
                            background: "rgba(82,196,26,0.65)",
                        }}
                    />
                    <div
                        style={{
                            position: "absolute",
                            bottom: "env(safe-area-inset-bottom)",
                            left: 0,
                            right: 0,
                            height: "1px",
                            background: "rgba(82,196,26,0.65)",
                        }}
                    />
                    {probeSnapshot.rects?.stage && (
                        <div
                            style={{
                                position: "absolute",
                                top: `${probeSnapshot.rects.stage.top}px`,
                                left: `${probeSnapshot.rects.stage.left}px`,
                                width: `${probeSnapshot.rects.stage.width}px`,
                                height: `${probeSnapshot.rects.stage.height}px`,
                                outline: "1px solid rgba(64,169,255,0.85)",
                                background: "rgba(64,169,255,0.05)",
                            }}
                        />
                    )}
                    {probeSnapshot.rects?.activeCard && (
                        <div
                            style={{
                                position: "absolute",
                                top: `${probeSnapshot.rects.activeCard.top}px`,
                                left: `${probeSnapshot.rects.activeCard.left}px`,
                                width: `${probeSnapshot.rects.activeCard.width}px`,
                                height: `${probeSnapshot.rects.activeCard.height}px`,
                                outline: "2px solid rgba(250,173,20,0.9)",
                                background: "rgba(250,173,20,0.06)",
                            }}
                        />
                    )}
                    {probeSnapshot.rects?.activeCard && (
                        <>
                            <div
                                style={{
                                    position: "absolute",
                                    top: 0,
                                    left: 0,
                                    right: 0,
                                    height: `${Math.max(
                                        0,
                                        probeSnapshot.spacing.topDeadZone || 0
                                    )}px`,
                                    background: "rgba(255,77,79,0.08)",
                                }}
                            />
                            <div
                                style={{
                                    position: "absolute",
                                    left: 0,
                                    right: 0,
                                    bottom: 0,
                                    height: `${Math.max(
                                        0,
                                        probeSnapshot.spacing.bottomDeadZone || 0
                                    )}px`,
                                    background: "rgba(255,77,79,0.08)",
                                }}
                            />
                        </>
                    )}
                    <div
                        style={{
                            position: "absolute",
                            left: "8px",
                            bottom: "8px",
                            padding: "6px 8px",
                            border: "1px solid rgba(255,255,255,0.18)",
                            borderRadius: "6px",
                            background: "rgba(0,0,0,0.58)",
                            fontSize: "10px",
                            lineHeight: 1.45,
                        }}
                    >
                        <div>museum probe</div>
                        <div>{probeSnapshot.orientation}</div>
                        <div>vh {Math.round(probeSnapshot.viewport.visualViewportHeight || 0)}</div>
                        <div>inner {probeSnapshot.viewport.innerHeight}</div>
                        <div>deltaY {probeSnapshot.center.deltaY ?? "-"}</div>
                        <div>top {probeSnapshot.spacing.topDeadZone ?? "-"}</div>
                        <div>bottom {probeSnapshot.spacing.bottomDeadZone ?? "-"}</div>
                    </div>
                </div>
            )}

            <div
                ref={containerRef}
                style={{
                    height: "100dvh",
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
                        onClick={() =>
                            setMode(
                                selectMuseumMode(
                                    MUSEUM_MODES.FICHAS
                                )
                            )
                        }
                        style={{
                            padding: "10px",
                            borderRadius: "50%",
                            border: "1px solid #333",
                            background: mode === MUSEUM_MODES.FICHAS ? "#fff" : "#111",
                            color: mode === MUSEUM_MODES.FICHAS ? "#000" : "#fff",
                            cursor: "pointer",
                            width: "44px",
                            height: "44px",
                        }}
                    >
                        ▭
                    </button>

                    <button
                        onClick={() =>
                            setMode(
                                selectMuseumMode(
                                    MUSEUM_MODES.TAP
                                )
                            )
                        }
                        style={{
                            padding: "10px",
                            borderRadius: "50%",
                            border: "1px solid #333",
                            background: mode === MUSEUM_MODES.TAP ? "#fff" : "#111",
                            color: mode === MUSEUM_MODES.TAP ? "#000" : "#fff",
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
                            minWidth: edgeSpacer,
                        }}
                    />

                    {data.map((item) => (
                        <BeerCoverV2
                            key={item.id}
                            beer={item}
                            scrollLeft={scrollLeft}
                            containerWidth={containerWidth}
                            onClick={() => setActiveItem(selectionRef.current.selectArtwork(item))}
                        />
                    ))}

                    <div
                        style={{
                            minWidth: edgeSpacer,
                        }}
                    />
                </>
            </div>

            {activeItem && (
                <div
                    onClick={() => setActiveItem(selectionRef.current.clearSelection())}
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
