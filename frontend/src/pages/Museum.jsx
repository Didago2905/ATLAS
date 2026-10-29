import { useState, useEffect, useLayoutEffect, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import BeerCoverV2 from "../components/BeerCoverV2";
import DismissibleArtworkOverlay from "../museum/presentation/DismissibleArtworkOverlay";
import { readBackgroundPreference } from "../backgrounds";
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

const COLLECTIONS = [
    { mode: MUSEUM_MODES.TAP, category: "tap_list", label: "Tablas", icon: "▦", fallbackRatio: 220 / 300, maxWidth: 220 },
    { mode: MUSEUM_MODES.FICHAS, category: "carta_vieja", label: "Cartas Viejas", icon: "▭", fallbackRatio: 220 / 300, maxWidth: 600 },
    { mode: MUSEUM_MODES.CARTAS_NUEVAS, category: "carta_nueva", label: "Cartas Nuevas", icon: "▤", fallbackRatio: 16 / 9, maxWidth: 600 },
    { mode: MUSEUM_MODES.ETIQUETAS, category: "etiquetas", label: "Etiquetas", icon: "◇", fallbackRatio: 4 / 3, maxWidth: 600 },
];
const LEGACY_CATEGORIES = {
    "fichas/antiguas": "carta_vieja",
    "fichas/actuales": "carta_nueva",
    tap: "tap_list",
    botellas: "etiquetas",
};

export default function Museum() {
    const navigate = useNavigate();
    const museumProbe = window.__ATLAS_MUSEUM_PROBE__ === true;

    const logMuseumQa = (...args) => {
        if (museumProbe) {
            console.log("[MUSEUM_QA]", ...args);
        }
    };

    logMuseumQa("Museum component mounted");

    const [mode, setMode] = useState(
        MUSEUM_MODES.FICHAS
    );
    const [museumData, setMuseumData] = useState([]);
    const [museumLoading, setMuseumLoading] = useState(true);
    const [museumError, setMuseumError] = useState("");
    const [activeItem, setActiveItem] = useState(null);
    const [probeSnapshot, setProbeSnapshot] = useState(null);
    const [searchOpen, setSearchOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [ordering, setOrdering] = useState("original");
    const [styleFilter, setStyleFilter] = useState("");
    const [breweryFilter, setBreweryFilter] = useState("");
    const searchTriggerRef = useRef(null);
    const searchPanelRef = useRef(null);
    const searchInputRef = useRef(null);
    const keyboardViewportRef = useRef(null);
    const [panelViewport, setPanelViewport] = useState(() => ({
        height: window.visualViewport?.height || window.innerHeight,
        offsetTop: window.visualViewport?.offsetTop || 0,
    }));

    const closeSearch = (returnFocus = true) => {
        searchInputRef.current?.blur();
        setSearchOpen(false);
        if (returnFocus) searchTriggerRef.current?.focus({ preventScroll: true });
    };
    const clearFilters = () => {
        setQuery("");
        setOrdering("original");
        setStyleFilter("");
        setBreweryFilter("");
    };
    const normalizeSearch = value => (typeof value === "string" ? value : "")
        .normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es").trim();
    const collator = useMemo(() => new Intl.Collator("es", { sensitivity: "base", numeric: true }), []);
    const searchIndex = useMemo(() => new Map(museumData.map(item => {
        let products = [];
        try {
            const parsed = typeof item.semantic_products === "string"
                ? JSON.parse(item.semantic_products) : item.semantic_products;
            if (Array.isArray(parsed)) products = parsed.filter(p => p && typeof p === "object" && !Array.isArray(p));
        } catch { /* A malformed semantic record must not hide its artwork. */ }
        const value = field => typeof field?.value === "string" ? field.value.trim() : "";
        const confirmed = field => field?.confidence === "confirmed" ? value(field) : "";
        const indexedProducts = products.map(product => ({
            name: value(product.beer_name),
            style: value(product.beer_style),
            brewery: confirmed(product.brewery),
            origin: confirmed(product.brewery_origin),
        }));
        if (!indexedProducts.length && typeof item.style === "string" && item.style.trim()) {
            indexedProducts.push({ name: "", style: item.style.trim(), brewery: "", origin: "" });
        }
        return [item.id, {
            products: indexedProducts.map(p => ({ ...p, styleKey: normalizeSearch(p.style), breweryKey: normalizeSearch(p.brewery) })),
            text: normalizeSearch([item.name, item.style,
                ...indexedProducts.flatMap(p => [p.name, p.style, p.brewery, p.origin])].filter(v => typeof v === "string").join(" ")),
        }];
    })), [museumData]);

    // Keyboard height changes must not rotate/reframe the coverflow. Width changes
    // still permit genuine orientation/layout changes; height restores on resize.
    const readGeometryViewport = () => {
        const dimensions = readViewportDimensions();
        const saved = keyboardViewportRef.current;
        if (saved && dimensions.width === saved.width
            && (document.activeElement === searchInputRef.current || dimensions.height < saved.height - 80)) return null;
        keyboardViewportRef.current = null;
        return dimensions;
    };

    const selectionRef = useRef(null);

    if (!selectionRef.current) {
        selectionRef.current = createSelection();
    }

    const requestCloseArtwork = () => {
        const selectedArtwork = selectionRef.current.clearSelection();
        window.__ATLAS_MUSEUM_MOTION_PROBE__
            ?.markSelectionChange({ artworkId: null });
        setActiveItem(selectedArtwork);
    };

    const [showUI, setShowUI] = useState(true);
    const [selectedBackground] = useState(readBackgroundPreference);

    const containerRef = useRef(null);
    const centeredCardRef = useRef(null);
    const geometryModeRef = useRef(mode);
    const [imageRatios, setImageRatios] = useState({});
    const [viewportHeight, setViewportHeight] = useState(() => readViewportDimensions().height);

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

    const getNearestCardNode = () => {
        const container = containerRef.current;

        if (!container) return null;

        const centerX =
            container.getBoundingClientRect().left +
            container.clientWidth / 2;

        const track = container.querySelector("[data-atlas-museum-track]");
        const cards = Array.from(track?.children || []).filter(
            node => node.querySelector("img")
        );

        return cards.reduce((nearest, card) => {
            if (!nearest) return card;

            const cardCenter = (node) => {
                const rect = node.getBoundingClientRect();
                return rect.left + rect.width / 2;
            };

            return Math.abs(cardCenter(card) - centerX) <
                Math.abs(cardCenter(nearest) - centerX)
                ? card
                : nearest;
        }, null);
    };

    // 🔥 FIX REAL AQUÍ
    useEffect(() => {

        logMuseumQa("useEffect entered");

        requestAnimationFrame(() => {
            logMuseumQa(
                "containerRef after RAF",
                containerRef.current
            );
        });

        const container = containerRef.current;

        if (!container) {
            logMuseumQa("containerRef is NULL");
            return;
        }

        logMuseumQa("containerRef OK");

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
            centeredCardRef.current = getNearestCardNode()?.dataset.atlasMuseumCardId ?? null;

            if (museumProbe) {
                console.log("[MUSEUM_QA][SCROLL]", {
                    scrollLeft: container.scrollLeft,
                    scrollWidth: container.scrollWidth,
                    clientWidth: container.clientWidth,
                });
            }

            logMuseumProbe("museum-scroll");
        };

        const handleResize = () => {
            const dimensions = readGeometryViewport();
            if (!dimensions) return;
            const width = getStageDimensions(measureStageWidth(container)).width;
            if (width !== 0) {
                setContainerWidth(width);
            }
            setViewportHeight(dimensions.height);
        };

        logMuseumQa("Scroll listener attached");

        const stopObservingScroll =
            observeStageScroll(container, handleScroll);
        const stopObservingResize =
            observeWindowResize(handleResize);

        return () => {
            stopObservingScroll();
            stopObservingResize();
        };

    }, []);

    useEffect(() => {
        const motionProbeEnabled =
            new URLSearchParams(window.location.search).get("motionProbe") === "1";

        if (!motionProbeEnabled || !containerRef.current) return;

        let cancelled = false;
        let uninstallProbe = null;
        let uninstallProbeControls = null;

        Promise.all([
            import("../museum/diagnostics/museumMotionProbe"),
            import("../museum/diagnostics/museumMotionProbeControls"),
        ])
            .then(([{ installMuseumMotionProbe }, { installMuseumMotionProbeControls }]) => {
                if (cancelled) return;
                uninstallProbe = installMuseumMotionProbe(containerRef.current);
                uninstallProbeControls = installMuseumMotionProbeControls();
            })
            .catch(error => {
                console.error("Museum motion probe failed to load:", error);
            });

        return () => {
            cancelled = true;
            uninstallProbeControls?.();
            uninstallProbe?.();
        };
    }, [museumData]);

    const readMuseumProbeSnapshot = (phase) => {
        const container = containerRef.current;
        const activeCard = getNearestCardNode();
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
            const dimensions = readGeometryViewport();
            if (dimensions) setIsLandscape(getViewport(dimensions).isLandscape);
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
        const controller = new AbortController();
        fetch("/api/public/museum", { signal: controller.signal })
            .then(res => {
                if (!res.ok) throw new Error(`Museum HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (!Array.isArray(data)) throw new Error("Invalid Museum archive");
                if (!controller.signal.aborted) setMuseumData(data);
            })
            .catch(err => {
                if (!controller.signal.aborted) {
                    console.error("Museum fetch error:", err);
                    setMuseumError("No se pudo cargar el archivo del Museo.");
                }
            })
            .finally(() => {
                if (!controller.signal.aborted) setMuseumLoading(false);
            });
        return () => controller.abort();
    }, []);

    // One existing auto-hide timer owns all navigation controls.
    useEffect(() => {
        let timeout;
        if (searchOpen) showControls(setShowUI);

        const hideUI = () => {
            if (searchOpen) return;
            hideControls(setShowUI);

            clearTimeout(timeout);
            timeout = setTimeout(() => {
                showControls(setShowUI);
            }, 450);
        };

        window.addEventListener("scroll", hideUI, { passive: true });
        window.addEventListener("touchmove", hideUI, { passive: true });

        return () => {
            clearTimeout(timeout);
            window.removeEventListener("scroll", hideUI);
            window.removeEventListener("touchmove", hideUI);
        };
    }, [searchOpen]);

    useEffect(() => {
        if (!searchOpen) return;
        const outside = event => {
            if (!searchPanelRef.current?.contains(event.target)
                && !searchTriggerRef.current?.contains(event.target)) closeSearch(false);
        };
        const escape = event => {
            if (event.key === "Escape") { event.preventDefault(); closeSearch(); }
        };
        const resize = () => {
            const next = { height: window.visualViewport?.height || window.innerHeight, offsetTop: window.visualViewport?.offsetTop || 0 };
            setPanelViewport(previous => previous.height === next.height && previous.offsetTop === next.offsetTop ? previous : next);
        };
        resize();
        document.addEventListener("pointerdown", outside);
        document.addEventListener("keydown", escape);
        window.addEventListener("resize", resize);
        window.visualViewport?.addEventListener("resize", resize);
        window.visualViewport?.addEventListener("scroll", resize);
        return () => {
            document.removeEventListener("pointerdown", outside);
            document.removeEventListener("keydown", escape);
            window.removeEventListener("resize", resize);
            window.visualViewport?.removeEventListener("resize", resize);
            window.visualViewport?.removeEventListener("scroll", resize);
        };
    }, [searchOpen]);

    const exhibitionArtworks = useMemo(() => createExhibition(createArchive(museumData)), [museumData]);

    const collection = COLLECTIONS.find(item => item.mode === mode);
    const collectionData = useMemo(() => exhibitionArtworks.filter(item => {
        const category = item?.category ?? LEGACY_CATEGORIES[item?.type] ?? item?.type;
        return category === collection.category;
    }), [exhibitionArtworks, mode]);
    const filterOptions = useMemo(() => {
        const styles = new Map(), breweries = new Map();
        for (const item of collectionData) {
            for (const product of searchIndex.get(item.id)?.products || []) {
                if (product.styleKey && !styles.has(product.styleKey)) styles.set(product.styleKey, product.style);
                if (product.breweryKey && !breweries.has(product.breweryKey)) breweries.set(product.breweryKey, product.brewery);
            }
        }
        const sorted = values => [...values].sort((a, b) => collator.compare(a[1], b[1]));
        return { styles: sorted(styles), breweries: sorted(breweries) };
    }, [collectionData, searchIndex, collator]);
    const data = useMemo(() => {
        const terms = normalizeSearch(query).split(/\s+/).filter(Boolean);
        const filtered = collectionData.filter(item => {
            const indexed = searchIndex.get(item.id);
            const matchesProduct = (!styleFilter && !breweryFilter)
                || indexed?.products.some(p => (!styleFilter || p.styleKey === styleFilter)
                    && (!breweryFilter || p.breweryKey === breweryFilter));
            return matchesProduct && terms.every(term => indexed?.text.includes(term));
        });
        if (ordering !== "original") filtered.sort((a, b) => {
            const left = typeof a.name === "string" ? a.name.trim() : "";
            const right = typeof b.name === "string" ? b.name.trim() : "";
            if (!left || !right) return left ? -1 : right ? 1 : 0;
            return collator.compare(left, right) * (ordering === "az" ? 1 : -1);
        });
        return filtered;
    }, [collectionData, searchIndex, query, ordering, styleFilter, breweryFilter, collator]);

    const stageWidth = containerWidth || readViewportDimensions().width;
    const compactToolbar = !isLandscape && stageWidth < 380;
    const panelTop = panelViewport.offsetTop + (isLandscape ? 68 : compactToolbar ? 140 : 92);
    const fieldStyle = { width: "100%", minHeight: "44px", boxSizing: "border-box", padding: "8px", border: "1px solid #666", borderRadius: "6px", background: "#181818", color: "#fff", fontSize: "16px" };
    const filterLabelStyle = { display: "grid", gridTemplateColumns: "88px minmax(0, 1fr)", alignItems: "center", gap: "8px" };
    const maxHeight = Math.max(1, Math.min(300, viewportHeight - (isLandscape ? 32 : 176)));
    const maxWidth = Math.max(1, Math.min(collection.maxWidth, stageWidth - (isLandscape ? 192 : 48)));
    const gap = isLandscape ? 64 : 52; // Includes the previous 12px margins on both cards.
    const paddingLeft = isLandscape ? 80 : 10;
    const paddingRight = 10;
    const frames = data.map(item => {
        const width = Number(item.manifest_metadata?.width ?? item.width);
        const height = Number(item.manifest_metadata?.height ?? item.height);
        const metadataRatio = width > 0 && height > 0 && Number.isFinite(width / height) ? width / height : null;
        const ratio = imageRatios[item.id] ?? metadataRatio ?? collection.fallbackRatio;
        // Fit the image's content box, then add the same 8px safety margin on every side.
        // Applying the aspect ratio to the outer padded frame would introduce letterboxing.
        const imageWidth = Math.min(Math.max(1, maxWidth - 16), Math.max(1, maxHeight - 16) * ratio);
        return { width: imageWidth + 16, height: imageWidth / ratio + 16 };
    });
    const edgeStart = Math.max(0, (stageWidth - (frames[0]?.width ?? 0)) / 2 - paddingLeft - gap) + 2;
    const edgeEnd = Math.max(0, (stageWidth - (frames.at(-1)?.width ?? 0)) / 2 - paddingRight - gap) + 2;
    const geometryKey = data.map((item, i) => `${item.id}:${frames[i].width}:${frames[i].height}`).join("|");

    useLayoutEffect(() => {
        const stage = containerRef.current;
        const cards = [...stage.querySelectorAll("[data-atlas-museum-card]")];
        const previousId = geometryModeRef.current === mode ? centeredCardRef.current : null;
        const card = cards.find(node => node.dataset.atlasMuseumCardId === previousId) ?? cards[0];
        geometryModeRef.current = mode;
        if (!card) {
            centeredCardRef.current = null;
            stage.scrollTo({ left: 0, behavior: "instant" });
            return;
        }
        // Size changes must preserve the centered artwork, including late legacy image loads.
        stage.scrollTo({ left: card.offsetLeft + card.offsetWidth / 2 - stage.clientWidth / 2, behavior: "instant" });
        centeredCardRef.current = card.dataset.atlasMuseumCardId;
    }, [geometryKey, mode, stageWidth]);

    const rememberImageRatio = (item, width, height) => {
        if (!(width > 0 && height > 0)) return;
        const ratio = width / height;
        setImageRatios(previous => previous[item.id] === ratio ? previous : { ...previous, [item.id]: ratio });
    };

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

            <button
                type="button"
                aria-label="Volver"
                title="Volver"
                data-atlas-museum-back
                tabIndex={showUI ? 0 : -1}
                onClick={() => {
                    if ((window.history.state?.idx ?? 0) > 0) navigate(-1);
                    else navigate("/", { replace: true });
                }}
                style={{
                    position: "fixed",
                    top: "calc(env(safe-area-inset-top, 0px) + 12px)",
                    left: "calc(env(safe-area-inset-left, 0px) + 12px)",
                    width: "44px",
                    height: "44px",
                    padding: 0,
                    display: "grid",
                    placeItems: "center",
                    zIndex: 100000,
                    border: 0,
                    background: "transparent",
                    color: "#fff",
                    opacity: showUI ? 1 : 0,
                    pointerEvents: showUI ? "auto" : "none",
                    transition: "opacity 0.25s ease",
                    cursor: "pointer",
                    WebkitTapHighlightColor: "transparent",
                    userSelect: "none",
                }}
            >
                <svg aria-hidden="true" focusable="false" width="24" height="24" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                    style={{ display: "block" }}>
                    <path d="M19 12H5m7 7-7-7 7-7" />
                </svg>
            </button>

            <button
                ref={searchTriggerRef}
                type="button"
                aria-label="Buscar en el Museo"
                title="Buscar en el Museo"
                aria-expanded={searchOpen}
                aria-controls="museum-search-panel"
                data-atlas-museum-search
                tabIndex={showUI ? 0 : -1}
                onClick={() => {
                    if (searchOpen) closeSearch();
                    else {
                        requestCloseArtwork();
                        setSearchOpen(true);
                    }
                }}
                style={{
                    position: "fixed",
                    top: "calc(env(safe-area-inset-top, 0px) + 12px)",
                    right: "calc(env(safe-area-inset-right, 0px) + 12px)",
                    width: "44px", height: "44px", padding: 0,
                    display: "grid", placeItems: "center", zIndex: 100000,
                    border: 0, background: "transparent", color: "#fff", cursor: "pointer",
                    opacity: showUI ? 1 : 0, pointerEvents: showUI ? "auto" : "none",
                    transition: "opacity 0.25s ease", WebkitTapHighlightColor: "transparent",
                }}
            >
                <svg aria-hidden="true" focusable="false" width="24" height="24" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                    style={{ display: "block" }}>
                    <circle cx="10.5" cy="10.5" r="6.5" />
                    <path d="m16 16 5 5" />
                </svg>
            </button>

            {searchOpen && (
                <section
                    id="museum-search-panel"
                    ref={searchPanelRef}
                    role="region"
                    aria-label="Explorar Museo"
                    onBlur={event => {
                        if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)
                            && !searchTriggerRef.current?.contains(event.relatedTarget)) closeSearch(false);
                    }}
                    style={{
                        position: "fixed", top: `calc(${panelTop}px + env(safe-area-inset-top, 0px))`,
                        right: "calc(env(safe-area-inset-right, 0px) + 12px)",
                        width: "min(340px, calc(100vw - 24px - env(safe-area-inset-left, 0px) - env(safe-area-inset-right, 0px)))",
                        maxHeight: `max(0px, calc(${Math.max(0, panelViewport.height - (panelTop - panelViewport.offsetTop) - 12)}px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px)))`,
                        overflowY: "auto", overscrollBehavior: "contain", boxSizing: "border-box",
                        zIndex: 100001, padding: "12px", border: "1px solid #555", borderRadius: "12px",
                        background: "rgba(15,15,15,0.97)", color: "#fff", display: "grid", gap: "8px",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <strong>Explorar Museo</strong>
                        <button type="button" aria-label="Cerrar búsqueda" onClick={() => closeSearch()}
                            style={{ minWidth: "44px", minHeight: "44px", padding: 0 }}>×</button>
                    </div>
                    <label style={filterLabelStyle}>
                        Orden
                        <select aria-label="Orden del Museo" value={ordering} onChange={event => setOrdering(event.target.value)} style={fieldStyle}>
                            <option value="original">Original</option>
                            <option value="az">A–Z</option>
                            <option value="za">Z–A</option>
                        </select>
                    </label>
                    <label style={filterLabelStyle}>
                        Estilo
                        <select aria-label="Estilo de cerveza" value={styleFilter} onChange={event => setStyleFilter(event.target.value)}
                            disabled={!filterOptions.styles.length} style={fieldStyle}>
                            <option value="">Todos los estilos</option>
                            {filterOptions.styles.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                        </select>
                    </label>
                    <label style={filterLabelStyle}>
                        Cervecería
                        <select aria-label="Cervecería" value={breweryFilter} onChange={event => setBreweryFilter(event.target.value)}
                            disabled={!filterOptions.breweries.length} style={fieldStyle}>
                            <option value="">Todas las cervecerías</option>
                            {filterOptions.breweries.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                        </select>
                    </label>
                    <small>Cervecería y origen: atribuciones confirmadas.</small>
                    <hr style={{ width: "100%", margin: "2px 0", border: 0, borderTop: "1px solid #444" }} />
                    <label style={{ display: "grid", gap: "4px" }}>
                        Buscar obras
                        <input ref={searchInputRef} type="search" aria-label="Buscar obras" value={query}
                            placeholder="Nombre, estilo, cervecería u origen"
                            onChange={event => setQuery(event.target.value)}
                            onFocus={() => {
                                keyboardViewportRef.current = { width: window.innerWidth, height: window.innerHeight };
                            }}
                            style={fieldStyle} />
                    </label>
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                        <span role="status" aria-live="polite" aria-atomic="true" style={{ fontSize: "14px" }}>{data.length} de {collectionData.length} obras</span>
                        <button type="button" onClick={clearFilters} style={{ minHeight: "44px", padding: "8px", fontSize: "14px" }}>Limpiar filtros</button>
                    </div>
                </section>
            )}

            <div
                ref={containerRef}
                data-atlas-museum-stage
                style={{
                    height: "100dvh",
                    background: selectedBackground.value,
                    overflowX: "auto",
                    scrollSnapType: "x mandatory",
                    scrollBehavior: "smooth",
                    position: "relative",
                }}
            >

                {/* SELECTOR */}
                <div
                    data-atlas-museum-selector
                    style={{
                        position: "fixed",
                        // At narrow widths the selector occupies its own row between the two icons.
                        top: isLandscape ? "max(50%, calc(env(safe-area-inset-top, 0px) + 179px))" : "20px",
                        ...(compactToolbar ? { top: "calc(env(safe-area-inset-top, 0px) + 68px)" } : {}),
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
                    {COLLECTIONS.map(item => (
                        <button
                            key={item.category}
                            type="button"
                            aria-label={item.label}
                            title={item.label}
                            aria-pressed={mode === item.mode}
                            onClick={() => {
                                if (mode === item.mode) return;
                                requestCloseArtwork();
                                setStyleFilter("");
                                setBreweryFilter("");
                                setMode(selectMuseumMode(item.mode));
                            }}
                            style={{
                                padding: "10px",
                                borderRadius: "50%",
                                border: "1px solid #333",
                                background: mode === item.mode ? "#fff" : "#111",
                                color: mode === item.mode ? "#000" : "#fff",
                                cursor: "pointer",
                                width: "44px",
                                height: "44px",
                            }}
                        >
                            {item.icon}
                        </button>
                    ))}

                </div>

                {!data.length && (
                    <div
                        role={museumError ? "alert" : "status"}
                        style={{
                            position: "absolute",
                            inset: "0 24px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            textAlign: "center",
                            color: "#fff",
                            textShadow: "0 1px 3px #000",
                            pointerEvents: "none",
                        }}
                    >
                        <div>
                            <p style={{ margin: 0 }}>
                                {museumLoading ? "Cargando archivo…" : museumError || (collectionData.length
                                    ? "No hay obras que coincidan con los filtros." : "Esta colección todavía no tiene obras.")}
                            </p>
                            {!museumLoading && !museumError && collectionData.length > 0 && (
                                <button type="button" onClick={clearFilters} style={{ display: "block", margin: "12px auto 0", minHeight: "44px", pointerEvents: "auto" }}>
                                    Limpiar filtros
                                </button>
                            )}
                        </div>
                    </div>
                )}

                <div
                    data-atlas-museum-track
                    style={{
                        display: "flex",
                        alignItems: "center",
                        width: "max-content",
                        minWidth: "100%",
                        height: "100%",
                        gap: `${gap}px`,
                        padding: `0 ${paddingRight}px 0 ${paddingLeft}px`,
                    }}
                >
                    <div
                        style={{
                            flex: `0 0 ${edgeStart}px`,
                            minWidth: `${edgeStart}px`,
                        }}
                    />

                    {data.map((item, index) => (
                        <BeerCoverV2
                            key={item.id}
                            beer={item}
                            stageRef={containerRef}
                            frame={frames[index]}
                            onImageDimensions={(width, height) => rememberImageRatio(item, width, height)}
                            visualScale={isLandscape ? 0.95 : 1}
                            onClick={() => {
                                closeSearch(false);
                                const selectedArtwork =
                                    selectionRef.current.selectArtwork(item);
                                window.__ATLAS_MUSEUM_MOTION_PROBE__
                                    ?.markSelectionChange({
                                        artworkId: selectedArtwork?.id ?? null,
                                    });
                                setActiveItem(selectedArtwork);
                            }}
                        />
                    ))}

                    <div
                        style={{
                            flex: `0 0 ${edgeEnd}px`,
                            minWidth: `${edgeEnd}px`,
                        }}
                    />
                </div>
            </div>

            {activeItem && (
                <DismissibleArtworkOverlay
                    artwork={activeItem}
                    background={selectedBackground.value}
                    onDismiss={requestCloseArtwork}
                />
            )}
        </>
    );
}
