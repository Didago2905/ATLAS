import { useParams, useNavigate } from "react-router-dom";
import useCatalogSession from "../catalog/useCatalogSession";
import BeerCard from "../components/BeerCard";
import { useState, useEffect, useRef, useLayoutEffect } from "react";
import { useLocation } from "react-router-dom";

export default function BeerDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const location = useLocation();

    const beersFromState = location.state?.beers;
    const indexFromState = location.state?.currentIndex;

    const [stableBeers, setStableBeers] = useState(null);

    const { beers: fallbackBeers } = useCatalogSession();
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
    const [artVisible, setArtVisible] = useState(false);
    const [layoutSnapshot, setLayoutSnapshot] = useState(null);
    const [stageBootstrapped, setStageBootstrapped] = useState(false);

    const startX = useRef(0);
    const startY = useRef(0);
    const axisLock = useRef(null);
    const multiTouchActive = useRef(false);
    const outerRef = useRef(null);
    const wrapperRef = useRef(null);
    const shellRef = useRef(null);
    const stageRef = useRef(null);
    const infoLayerRef = useRef(null);
    const beerCardRef = useRef(null);
    const artOverlayRef = useRef(null);
    const stageLifecycleStartRef = useRef(performance.now());

    const isMobile = window.innerWidth < 768;
    const spatialDebug = window.__ATLAS_SPATIAL_PROBE__ === true;
    const viewportProbe = window.__ATLAS_VIEWPORT_PROBE__ === true;

    const debugOutline = (color) =>
        spatialDebug
            ? {
                outline: `2px solid ${color}`,
                outlineOffset: "-2px",
            }
            : {};

    const logRootGeometry = (phase, extra = {}) => {
        if (!viewportProbe) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const readStyle = (node) => {
            if (!node) return null;

            const style = window.getComputedStyle(node);

            return {
                height: style.height,
                minHeight: style.minHeight,
                overflow: style.overflow,
                position: style.position,
                transform: style.transform,
            };
        };

        const describeNode = (node) => {
            if (!node) return null;

            return {
                tagName: node.tagName,
                id: node.id || null,
                className:
                    typeof node.className === "string"
                        ? node.className
                        : null,
            };
        };

        const root = document.getElementById("root");
        const outer = outerRef.current;
        const centerX = Math.round(window.innerWidth / 2);

        console.log("[root-geometry]", {
            phase,
            beerId: id,
            viewMode,
            timestamp: Math.round(performance.now()),
            scroll: {
                scrollX: window.scrollX,
                scrollY: window.scrollY,
                pageYOffset: window.pageYOffset,
                documentScrollTop: document.documentElement.scrollTop,
                bodyScrollTop: document.body.scrollTop,
            },
            viewport: {
                innerHeight: window.innerHeight,
                visualViewportHeight: window.visualViewport?.height,
                visualViewportOffsetTop: window.visualViewport?.offsetTop,
                visualViewportPageTop: window.visualViewport?.pageTop,
            },
            rects: {
                html: toRect(document.documentElement),
                body: toRect(document.body),
                root: toRect(root),
                outer: toRect(outer),
            },
            computed: {
                html: readStyle(document.documentElement),
                body: readStyle(document.body),
                root: readStyle(root),
                outer: readStyle(outer),
            },
            outer: {
                offsetTop: outer?.offsetTop ?? null,
                offsetParent: describeNode(outer?.offsetParent),
            },
            elementFromPoint: {
                top: describeNode(document.elementFromPoint(centerX, 0)),
                y56: describeNode(document.elementFromPoint(centerX, 56)),
            },
            ...extra,
        });
    };

    const readBootstrapMetrics = () => {
        const viewportHeight =
            window.visualViewport?.height || window.innerHeight;
        const outerRect = outerRef.current?.getBoundingClientRect();
        const cardRect = beerCardRef.current?.getBoundingClientRect();

        return {
            scrollY: window.scrollY,
            pageYOffset: window.pageYOffset,
            documentScrollTop: document.documentElement.scrollTop,
            outerTop: outerRect ? Math.round(outerRect.top) : null,
            freeTop: cardRect ? Math.round(cardRect.top) : null,
            freeBottom: cardRect
                ? Math.round(viewportHeight - cardRect.bottom)
                : null,
            viewportPageTop: window.visualViewport?.pageTop,
        };
    };

    useLayoutEffect(() => {
        setStageBootstrapped(false);

        const before = readBootstrapMetrics();
        const shouldReset =
            before.scrollY > 0 ||
            before.pageYOffset > 0 ||
            before.documentScrollTop > 0;

        console.log("[immersive-bootstrap]", {
            phase: "before-reset",
            beerId: id,
            viewMode,
            resetNeeded: shouldReset,
            ...before,
        });

        if (shouldReset) {
            window.scrollTo(0, 0);
        }

        const frame = requestAnimationFrame(() => {
            const after = readBootstrapMetrics();

            console.log("[immersive-bootstrap]", {
                phase: "after-reset",
                beerId: id,
                viewMode,
                resetApplied: shouldReset,
                beforeScrollY: before.scrollY,
                afterScrollY: after.scrollY,
                beforeOuterTop: before.outerTop,
                afterOuterTop: after.outerTop,
                beforeFreeTop: before.freeTop,
                afterFreeTop: after.freeTop,
                beforeFreeBottom: before.freeBottom,
                afterFreeBottom: after.freeBottom,
                beforeViewportPageTop: before.viewportPageTop,
                afterViewportPageTop: after.viewportPageTop,
            });

            setStageBootstrapped(true);

            console.log("[immersive-bootstrap]", {
                phase: "ready",
                beerId: id,
                viewMode,
                ...after,
            });
        });

        return () => cancelAnimationFrame(frame);
    }, [id]);

    useEffect(() => {
        const html = document.documentElement;
        const body = document.body;

        html.classList.add("no-scroll");
        body.classList.add("no-scroll");

        return () => {
            html.classList.remove("no-scroll");
            body.classList.remove("no-scroll");
        };
    }, []);

    useEffect(() => {
        if (!viewportProbe || !stageBootstrapped) return;

        const readResetMetrics = () => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const outerRect = outerRef.current?.getBoundingClientRect();
            const stageRect = stageRef.current?.getBoundingClientRect();
            const cardRect = beerCardRef.current?.getBoundingClientRect();

            return {
                scrollY: window.scrollY,
                pageYOffset: window.pageYOffset,
                documentScrollTop: document.documentElement.scrollTop,
                outerTop: outerRect ? Math.round(outerRect.top) : null,
                stageTop: stageRect ? Math.round(stageRect.top) : null,
                freeTop: cardRect ? Math.round(cardRect.top) : null,
                freeBottom: cardRect
                    ? Math.round(viewportHeight - cardRect.bottom)
                    : null,
                viewportPageTop: window.visualViewport?.pageTop,
            };
        };

        const before = readResetMetrics();
        const shouldReset =
            before.scrollY > 0 ||
            before.pageYOffset > 0 ||
            before.documentScrollTop > 0;

        if (!shouldReset) {
            console.log("[root-scroll-reset]", {
                phase: "skipped",
                beerId: id,
                viewMode,
                timestamp: Math.round(performance.now()),
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                beforeScrollY: before.scrollY,
                beforePageYOffset: before.pageYOffset,
                beforeDocumentScrollTop: before.documentScrollTop,
                beforeOuterTop: before.outerTop,
                beforeFreeTop: before.freeTop,
                beforeStageTop: before.stageTop,
                beforeViewportPageTop: before.viewportPageTop,
            });
            return;
        }

        window.scrollTo(0, 0);

        const frame = requestAnimationFrame(() => {
            const after = readResetMetrics();

            console.log("[root-scroll-reset]", {
                phase: "after-scrollTo",
                beerId: id,
                viewMode,
                timestamp: Math.round(performance.now()),
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                beforeScrollY: before.scrollY,
                afterScrollY: after.scrollY,
                beforePageYOffset: before.pageYOffset,
                afterPageYOffset: after.pageYOffset,
                beforeDocumentScrollTop: before.documentScrollTop,
                afterDocumentScrollTop: after.documentScrollTop,
                beforeOuterTop: before.outerTop,
                afterOuterTop: after.outerTop,
                beforeFreeTop: before.freeTop,
                afterFreeTop: after.freeTop,
                beforeFreeBottom: before.freeBottom,
                afterFreeBottom: after.freeBottom,
                beforeStageTop: before.stageTop,
                afterStageTop: after.stageTop,
                beforeViewportPageTop: before.viewportPageTop,
                afterViewportPageTop: after.viewportPageTop,
            });

            logRootGeometry("root-scroll-reset.after");
        });

        return () => cancelAnimationFrame(frame);
    }, [id, viewportProbe, stageBootstrapped]);

    useEffect(() => {
        if (beersFromState && !stableBeers) {
            setStableBeers(beersFromState);
        }
    }, [beersFromState]);

    useEffect(() => {
        const backgroundUrl = beer?.beercard_background_url;
        if (!backgroundUrl) return;

        const img = new Image();

        img.src = backgroundUrl;

        if (img.decode) {
            img.decode().catch(() => {});
        }

        return () => {
            img.onload = null;
            img.onerror = null;
        };
    }, [beer?.beercard_background_url]);

    useEffect(() => {

        [prevBeer, nextBeer].forEach((candidate) => {

            const url = candidate?.beercard_background_url;

            if (!url) return;

            const img = new Image();

            img.src = url;

            if (img.decode) {
                img.decode().catch(() => {});
            }

        });

    }, [
        prevBeer?.beercard_background_url,
        nextBeer?.beercard_background_url
    ]);

    useEffect(() => {
        setVisible(true);
    }, []);

    useEffect(() => {
        setAnimating(false);
        setDirection(null);
    }, [id]);

    useEffect(() => {
        stageLifecycleStartRef.current = performance.now();
    }, [id]);

    useEffect(() => {
        const logViewport = (phase) => {
            console.log("[viewport]", {
                phase,
                innerHeight: window.innerHeight,
                visualViewportHeight: window.visualViewport?.height,
                documentClientHeight: document.documentElement.clientHeight,
            });
        };

        logViewport("mount");

        const handleResize = () => {
            logViewport("resize");
        };

        window.visualViewport?.addEventListener("resize", handleResize);

        return () => {
            window.visualViewport?.removeEventListener("resize", handleResize);
        };
    }, []);

    useEffect(() => {
        if (!stageBootstrapped) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const logLayout = (phase) => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRect = beerCardRef.current?.getBoundingClientRect();

            const snapshot = {
                phase,
                viewport: {
                    innerHeight: window.innerHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    documentClientHeight: document.documentElement.clientHeight,
                },
                outerRect: toRect(outerRef.current),
                wrapperRect: toRect(wrapperRef.current),
                shellRect: toRect(shellRef.current),
                stageRect: toRect(stageRef.current),
                cardRect: toRect(beerCardRef.current),
                artOverlayRect: toRect(artOverlayRef.current),
                freeTop: cardRect ? Math.round(cardRect.top) : null,
                freeBottom: cardRect
                    ? Math.round(viewportHeight - cardRect.bottom)
                    : null,
            };

            console.log("[layout]", snapshot);

            if (spatialDebug) {
                setLayoutSnapshot(snapshot);
            }
        };

        logLayout("mount");

        const frame = requestAnimationFrame(() => {
            logLayout("frame");
        });

        const handleResize = () => {
            logLayout("viewport-resize");
        };

        window.visualViewport?.addEventListener("resize", handleResize);

        return () => {
            cancelAnimationFrame(frame);
            window.visualViewport?.removeEventListener("resize", handleResize);
        };
    }, [id, viewMode, spatialDebug, stageBootstrapped]);

    useEffect(() => {
        console.log("[viewMode]", {
            beerId: id,
            viewMode,
        });
    }, [id, viewMode]);

    useEffect(() => {
        if (!viewportProbe || !stageBootstrapped) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const logViewportLifecycle = (phase, extra = {}) => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRectRaw = beerCardRef.current?.getBoundingClientRect();
            const rootStyle = window.getComputedStyle(document.documentElement);

            console.log("[viewport-probe]", {
                phase,
                beerId: id,
                viewMode,
                timestamp: Math.round(performance.now()),
                viewport: {
                    innerHeight: window.innerHeight,
                    documentClientHeight: document.documentElement.clientHeight,
                    bodyClientHeight: document.body.clientHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    visualViewportOffsetTop: window.visualViewport?.offsetTop,
                    visualViewportPageTop: window.visualViewport?.pageTop,
                    atlasVh: rootStyle.getPropertyValue("--atlas-vh").trim(),
                },
                rects: {
                    outer: toRect(outerRef.current),
                    wrapper: toRect(wrapperRef.current),
                    stage: toRect(stageRef.current),
                    card: toRect(beerCardRef.current),
                },
                freeSpace: {
                    top: cardRectRaw ? Math.round(cardRectRaw.top) : null,
                    bottom: cardRectRaw
                        ? Math.round(viewportHeight - cardRectRaw.bottom)
                        : null,
                },
                body: {
                    noScroll: document.body.classList.contains("no-scroll"),
                },
                ...extra,
            });
        };

        logViewportLifecycle("mount");
        logRootGeometry("mount");

        let secondFrame = null;

        const firstFrame = requestAnimationFrame(() => {
            logViewportLifecycle("first-raf");
            logRootGeometry("first-raf");

            secondFrame = requestAnimationFrame(() => {
                logViewportLifecycle("second-raf");
                logRootGeometry("second-raf");
            });
        });

        const handleVisualViewportResize = () => {
            logViewportLifecycle("visualViewport.resize");
            logRootGeometry("visualViewport.resize");
        };

        const handleVisualViewportScroll = () => {
            logViewportLifecycle("visualViewport.scroll");
            logRootGeometry("visualViewport.scroll");
        };

        const handleWindowResize = () => {
            logViewportLifecycle("window.resize");
            logRootGeometry("window.resize");
        };

        const handleOrientationChange = () => {
            logViewportLifecycle("orientationchange");
        };

        const handlePageShow = (event) => {
            logViewportLifecycle("pageshow", {
                persisted: event.persisted,
            });
        };

        const bodyClassObserver = new MutationObserver(() => {
            const phase = document.body.classList.contains("no-scroll")
                ? "body.no-scroll.add"
                : "body.no-scroll.remove";

            logViewportLifecycle(phase);
            logRootGeometry(phase);
        });

        window.visualViewport?.addEventListener("resize", handleVisualViewportResize);
        window.visualViewport?.addEventListener("scroll", handleVisualViewportScroll);
        window.addEventListener("resize", handleWindowResize);
        window.addEventListener("orientationchange", handleOrientationChange);
        window.addEventListener("pageshow", handlePageShow);
        bodyClassObserver.observe(document.body, {
            attributes: true,
            attributeFilter: ["class"],
        });

        return () => {
            cancelAnimationFrame(firstFrame);
            if (secondFrame) {
                cancelAnimationFrame(secondFrame);
            }
            window.visualViewport?.removeEventListener("resize", handleVisualViewportResize);
            window.visualViewport?.removeEventListener("scroll", handleVisualViewportScroll);
            window.removeEventListener("resize", handleWindowResize);
            window.removeEventListener("orientationchange", handleOrientationChange);
            window.removeEventListener("pageshow", handlePageShow);
            bodyClassObserver.disconnect();
        };
    }, [id, viewMode, viewportProbe, stageBootstrapped]);

    useEffect(() => {
        if ((!viewportProbe && !spatialDebug) || !stageBootstrapped) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const readTransform = (node) =>
            node ? window.getComputedStyle(node).transform : null;

        const getStageSnapshot = (phase, previousRect = null) => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRectRaw = beerCardRef.current?.getBoundingClientRect();
            const stageRect = toRect(stageRef.current);
            const cardRect = toRect(beerCardRef.current);
            const stableRect =
                previousRect && stageRect
                    ? Math.abs(stageRect.top - previousRect.top) <= 1 &&
                    Math.abs(stageRect.height - previousRect.height) <= 1
                    : false;

            return {
                phase,
                beerId: id,
                viewMode,
                visible,
                animating,
                direction,
                artVisible,
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                viewport: {
                    innerHeight: window.innerHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    visualViewportOffsetTop: window.visualViewport?.offsetTop,
                },
                rects: {
                    outer: toRect(outerRef.current),
                    wrapper: toRect(wrapperRef.current),
                    shell: toRect(shellRef.current),
                    stage: stageRect,
                    card: cardRect,
                },
                freeSpace: {
                    top: cardRectRaw ? Math.round(cardRectRaw.top) : null,
                    bottom: cardRectRaw
                        ? Math.round(viewportHeight - cardRectRaw.bottom)
                        : null,
                },
                transforms: {
                    shell: readTransform(shellRef.current),
                    info: readTransform(infoLayerRef.current),
                    art: readTransform(artOverlayRef.current),
                },
                stability: {
                    stableRect,
                    previousStageTop: previousRect?.top ?? null,
                    currentStageTop: stageRect?.top ?? null,
                },
            };
        };

        const logStagePhase = (phase, previousRect = null) => {
            const snapshot = getStageSnapshot(phase, previousRect);
            console.log("[stage-phase]", snapshot);

            if (phase === "ready-check") {
                logRootGeometry("ready-check");
            }

            return snapshot.rects.stage;
        };

        const mountRect = logStagePhase("mounting");
        let secondFrame = null;
        let thirdFrame = null;

        const firstFrame = requestAnimationFrame(() => {
            const firstRect = logStagePhase("settling:first-raf", mountRect);

            secondFrame = requestAnimationFrame(() => {
                const secondRect = logStagePhase(
                    "candidate-ready",
                    firstRect
                );

                thirdFrame = requestAnimationFrame(() => {
                    logStagePhase("ready-check", secondRect);
                });
            });
        });

        return () => {
            cancelAnimationFrame(firstFrame);
            if (secondFrame) {
                cancelAnimationFrame(secondFrame);
            }
            if (thirdFrame) {
                cancelAnimationFrame(thirdFrame);
            }
        };
    }, [
        id,
        viewMode,
        visible,
        animating,
        direction,
        artVisible,
        viewportProbe,
        spatialDebug,
        stageBootstrapped,
    ]);

    useEffect(() => {
        if (viewMode !== "art") {
            setArtVisible(false);
            return;
        }

        console.log("[artTransition]", {
            beerId: id,
            phase: "mount",
        });

        setArtVisible(false);

        const frame = requestAnimationFrame(() => {
            setArtVisible(true);
            console.log("[artTransition]", {
                beerId: id,
                phase: "visible",
            });
        });

        return () => cancelAnimationFrame(frame);
    }, [id, viewMode]);

    const logStageTransitionEnd = (layer, event) => {
        if (!viewportProbe && !spatialDebug) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const getTransform = (node) =>
            node ? window.getComputedStyle(node).transform : null;

        const readPostTransitionSnapshot = () => {
            const viewportHeight =
                window.visualViewport?.height || window.innerHeight;
            const cardRectRaw = beerCardRef.current?.getBoundingClientRect();
            const stageRect = toRect(stageRef.current);

            return {
                phase: "post-transition-ready-check",
                layer,
                propertyName: event.propertyName,
                beerId: id,
                viewMode,
                visible,
                animating,
                direction,
                artVisible,
                elapsed: Math.round(
                    performance.now() - stageLifecycleStartRef.current
                ),
                viewport: {
                    innerHeight: window.innerHeight,
                    visualViewportHeight: window.visualViewport?.height,
                    visualViewportOffsetTop: window.visualViewport?.offsetTop,
                },
                rects: {
                    outer: toRect(outerRef.current),
                    wrapper: toRect(wrapperRef.current),
                    shell: toRect(shellRef.current),
                    stage: stageRect,
                    card: toRect(beerCardRef.current),
                },
                freeSpace: {
                    top: cardRectRaw ? Math.round(cardRectRaw.top) : null,
                    bottom: cardRectRaw
                        ? Math.round(viewportHeight - cardRectRaw.bottom)
                        : null,
                },
                transforms: {
                    shell: getTransform(shellRef.current),
                    info: getTransform(infoLayerRef.current),
                    art: getTransform(artOverlayRef.current),
                },
                stability: {
                    currentStageTop: stageRect?.top ?? null,
                    currentStageHeight: stageRect?.height ?? null,
                },
            };
        };

        console.log("[stage-phase]", {
            phase: "transitionend",
            layer,
            propertyName: event.propertyName,
            beerId: id,
            viewMode,
            visible,
            animating,
            direction,
            artVisible,
            elapsed: Math.round(
                performance.now() - stageLifecycleStartRef.current
            ),
            transforms: {
                shell: shellRef.current
                    ? window.getComputedStyle(shellRef.current).transform
                    : null,
                info: infoLayerRef.current
                    ? window.getComputedStyle(infoLayerRef.current).transform
                    : null,
                art: artOverlayRef.current
                    ? window.getComputedStyle(artOverlayRef.current).transform
                    : null,
            },
        });

        if (event.propertyName !== "transform") return;

        requestAnimationFrame(() => {
            console.log("[stage-phase]", readPostTransitionSnapshot());
            logRootGeometry("post-transition-ready-check", {
                layer,
                propertyName: event.propertyName,
            });
        });
    };

    if (!beers.length) {
        return <div style={{ height: "var(--atlas-vh, 100vh)", background: "#000" }} />;
    }

    if (!beer) {
        return <div style={{ height: "var(--atlas-vh, 100vh)", background: "#000" }} />;
    }

    return (
        <div
            ref={outerRef}
            style={{
                height: "var(--atlas-vh, 100vh)",
                background: "#000",
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                position: "relative",
                overflow: "hidden",
                paddingTop: 0,
                paddingBottom: 0,
                boxSizing: "border-box",
                ...debugOutline("rgba(255, 77, 79, 0.9)"),
            }}
        >
            {spatialDebug && (
                <>
                    <div
                        style={{
                            position: "fixed",
                            left: 0,
                            right: 0,
                            top: "50%",
                            height: "1px",
                            background: "rgba(255,255,255,0.55)",
                            zIndex: 999999,
                            pointerEvents: "none",
                        }}
                    />

                    <div
                        style={{
                            position: "fixed",
                            top: "10px",
                            right: "10px",
                            zIndex: 999999,
                            pointerEvents: "none",
                            background: "rgba(0,0,0,0.78)",
                            border: "1px solid rgba(255,255,255,0.25)",
                            borderRadius: "6px",
                            color: "#fff",
                            fontSize: "11px",
                            lineHeight: 1.45,
                            padding: "8px",
                            maxWidth: "210px",
                            fontFamily: "monospace",
                        }}
                    >
                        <div>spatial debug</div>
                        <div>phase: {layoutSnapshot?.phase || "-"}</div>
                        <div>vh: {Math.round(layoutSnapshot?.viewport?.visualViewportHeight || 0)}</div>
                        <div>inner: {layoutSnapshot?.viewport?.innerHeight || "-"}</div>
                        <div>freeTop: {layoutSnapshot?.freeTop ?? "-"}</div>
                        <div>freeBottom: {layoutSnapshot?.freeBottom ?? "-"}</div>
                        <div>cardH: {layoutSnapshot?.cardRect?.height ?? "-"}</div>
                        <div>stageTop: {layoutSnapshot?.stageRect?.top ?? "-"}</div>
                    </div>
                </>
            )}

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
                ref={wrapperRef}
                style={{
                    position: "relative",
                    width: "100%",
                    maxWidth: "600px",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    ...debugOutline("rgba(64, 169, 255, 0.9)"),
                }}
                onTouchStart={(e) => {
                    if (e.touches.length > 1) {
                        multiTouchActive.current = true;
                        axisLock.current = null;
                        console.log("[gesture]", {
                            type: "multiTouchCancel",
                            phase: "start",
                            touches: e.touches.length,
                        });
                        return;
                    }

                    multiTouchActive.current = false;
                    startX.current = e.touches[0].clientX;
                    startY.current = e.touches[0].clientY;
                    axisLock.current = null;

                    console.log("[gesture]", {
                        type: "touchStart",
                        beerId: id,
                        startX: startX.current,
                        startY: startY.current,
                        viewMode,
                    });

                    logRootGeometry("gesture.touchStart", {
                        startX: startX.current,
                        startY: startY.current,
                    });
                }}
                onTouchMove={(e) => {
                    if (e.touches.length > 1) {
                        if (!multiTouchActive.current) {
                            console.log("[gesture]", {
                                type: "multiTouchCancel",
                                phase: "move",
                                touches: e.touches.length,
                            });
                        }

                        multiTouchActive.current = true;
                        axisLock.current = null;
                        return;
                    }

                    if (multiTouchActive.current) return;

                    if (axisLock.current) return;

                    const currentX = e.touches[0].clientX;
                    const currentY = e.touches[0].clientY;
                    const deltaX = currentX - startX.current;
                    const deltaY = currentY - startY.current;
                    const absX = Math.abs(deltaX);
                    const absY = Math.abs(deltaY);
                    const lockThreshold = 14;
                    const ambiguityBuffer = 10;

                    if (absX < lockThreshold && absY < lockThreshold) return;

                    if (absX > absY + ambiguityBuffer) {
                        axisLock.current = "horizontal";
                    }

                    if (absY > absX + ambiguityBuffer) {
                        axisLock.current = "vertical";
                    }

                    if (axisLock.current) {
                        console.log("[gesture]", {
                            type: "axisLock",
                            axis: axisLock.current,
                            deltaX,
                            deltaY,
                        });
                    }
                }}
                onTouchEnd={(e) => {
                    if (multiTouchActive.current) {
                        axisLock.current = null;

                        console.log("[gesture]", {
                            type: "multiTouchEnd",
                            remainingTouches: e.touches.length,
                        });

                        if (e.touches.length === 0) {
                            multiTouchActive.current = false;
                        }

                        return;
                    }

                    const endX = e.changedTouches[0].clientX;
                    const endY = e.changedTouches[0].clientY;
                    const deltaX = endX - startX.current;
                    const deltaY = endY - startY.current;
                    const absX = Math.abs(deltaX);
                    const absY = Math.abs(deltaY);
                    const ambiguityBuffer = 10;
                    let action = "none";

                    if (!axisLock.current) {
                        if (absX > absY + ambiguityBuffer) {
                            axisLock.current = "horizontal";
                        }

                        if (absY > absX + ambiguityBuffer) {
                            axisLock.current = "vertical";
                        }
                    }

                    console.log("[gesture]", {
                        type: "touchEnd",
                        beerId: id,
                        endX,
                        endY,
                        axis: axisLock.current,
                        deltaX,
                        deltaY,
                        viewMode,
                    });

                    if (axisLock.current === "vertical") {
                        if (deltaY < -70 && viewMode !== "art") {
                            action = "art";
                            setViewMode("art");
                        }

                        if (deltaY > 70 && viewMode !== "info") {
                            action = "info";
                            setViewMode("info");
                        }

                        console.log("[gesture]", {
                            type: "action",
                            axis: "vertical",
                            action,
                            deltaX,
                            deltaY,
                        });

                        logRootGeometry("gesture.touchEnd", {
                            axis: "vertical",
                            action,
                            deltaX,
                            deltaY,
                        });

                        axisLock.current = null;
                        return;
                    }

                    if (axisLock.current !== "horizontal") {
                        console.log("[gesture]", {
                            type: "action",
                            axis: axisLock.current,
                            action,
                            deltaX,
                            deltaY,
                        });

                        logRootGeometry("gesture.touchEnd", {
                            axis: axisLock.current,
                            action,
                            deltaX,
                            deltaY,
                        });

                        axisLock.current = null;
                        return;
                    }

                    if (deltaX > 50 && prevBeer) {
                        action = "prev";
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
                        }, 0);
                    }

                    if (deltaX < -50 && nextBeer) {
                        action = "next";
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
                        }, 0);
                    }

                    console.log("[gesture]", {
                        type: "action",
                        axis: "horizontal",
                        action,
                        deltaX,
                        deltaY,
                    });

                    logRootGeometry("gesture.touchEnd", {
                        axis: "horizontal",
                        action,
                        deltaX,
                        deltaY,
                    });

                    axisLock.current = null;
                }}
                onTouchCancel={(e) => {
                    axisLock.current = null;
                    multiTouchActive.current = false;

                    console.log("[gesture]", {
                        type: "touchCancel",
                        touches: e.touches.length,
                    });
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
                        ref={shellRef}
                        onTransitionEnd={(event) =>
                            logStageTransitionEnd("shell", event)
                        }
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
                            ...debugOutline("rgba(115, 209, 61, 0.9)"),
                        }}
                    >
                        <div
                            ref={stageRef}
                            style={{
                                position: "relative",
                                width: "100%",
                                ...debugOutline("rgba(250, 173, 20, 0.9)"),
                            }}
                        >

                            {/* INFO */}
                            <div
                                ref={infoLayerRef}
                                onTransitionEnd={(event) =>
                                    logStageTransitionEnd("info", event)
                                }
                                style={{
                                    opacity: viewMode === "info" ? 1 : 0,
                                    transform: viewMode === "info" ? "scale(1)" : "scale(0.96)",
                                    transition: "all 0.25s ease",
                                }}
                            >
                                <BeerCard
                                    key={beer.id}
                                    beer={beer}
                                    layoutRef={beerCardRef}
                                    spatialDebug={spatialDebug}
                                />
                            </div>

                            {/* ARTE */}
                            {viewMode === "art" && (
                                <div
                                    ref={artOverlayRef}
                                    onTransitionEnd={(event) =>
                                        logStageTransitionEnd("art", event)
                                    }
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
                                        opacity: artVisible ? 1 : 0,
                                        transform: artVisible ? "scale(1)" : "scale(0.985)",
                                        transition: "opacity 0.22s ease, transform 0.22s cubic-bezier(0.22, 1, 0.36, 1)",
                                        ...debugOutline("rgba(235, 47, 150, 0.9)"),
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
