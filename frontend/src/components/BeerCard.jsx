import PeekOverlay from "./PeekOverlay";
import { formatABV } from "../utils/formatters";
import { resolveColor, colorLabelMap } from "../utils/colorUtils";
import { useState, useRef, useEffect } from "react";
import tasterGlass from "../assets/glassware/taster-120ml.webp";
import smallPintGlass from "../assets/glassware/pint-small-330ml.webp";
import largePintGlass from "../assets/glassware/pint-large-500ml.webp";
import smallPitcherGlass from "../assets/glassware/pitcher-small-1l.webp";
import largePitcherGlass from "../assets/glassware/pitcher-large-1-9l.webp";

const GLASSWARE = {
    taster: { src: tasterGlass, label: "Taster", capacity: "120 ML", size: 56, peekInset: "13% 16% 13% 16%" },
    pinta_chica: { src: smallPintGlass, label: "Pinta chica", capacity: "330 ML", size: 60, peekInset: "0% 19% 2% 19%" },
    pinta_grande: { src: largePintGlass, label: "Pinta grande", capacity: "500 ML", size: 64, peekInset: "4% 21% 4% 21%" },
    jarra_chica: { src: smallPitcherGlass, label: "Jarra chica", capacity: "1 L", size: 66, peekInset: "1% 4% 0% 11%" },
    jarra_grande: { src: largePitcherGlass, label: "Jarra grande", capacity: "1.7 L", size: 70, peekInset: "0% 0% 0% 10%" },
};

// Session-scoped registry of background URLs that have already completed loading.
const loadedBackgroundUrls = new Set();

// 🔥 detectar si el color es oscuro
const isDarkColor = (hex) => {
    if (!hex || !hex.startsWith("#")) return false;

    const r = parseInt(hex.substr(1, 2), 16);
    const g = parseInt(hex.substr(3, 2), 16);
    const b = parseInt(hex.substr(5, 2), 16);

    const luminance = (0.299 * r + 0.587 * g + 0.114 * b);
    return luminance < 60;
};

// 🔥 ajustar color
const adjustColorForUI = (hex) => {
    if (isDarkColor(hex)) {
        return "#444444";
    }
    return hex;
};

const withAlpha = (hex, alpha) => {
    if (!hex || !hex.startsWith("#")) return `rgba(255, 255, 255, ${alpha})`;

    const normalized = hex.length === 4
        ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}`
        : hex;

    const r = parseInt(normalized.slice(1, 3), 16);
    const g = parseInt(normalized.slice(3, 5), 16);
    const b = parseInt(normalized.slice(5, 7), 16);

    if (Number.isNaN(r) || Number.isNaN(g) || Number.isNaN(b)) {
        return `rgba(255, 255, 255, ${alpha})`;
    }

    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

export default function BeerCard({ beer, layoutRef, spatialDebug = false }) {

    const [peekAsset, setPeekAsset] = useState(null);
    const glassPeekOpenRef = useRef(false);
    const [showBrewery, setShowBrewery] = useState(false);

    const [showArt, setShowArt] = useState(false);
    const [backgroundLoaded, setBackgroundLoaded] = useState(() =>
        loadedBackgroundUrls.has(beer.beercard_background_url)
    );
    const lastTap = useRef(0);

    const panelRef = useRef(null);
    const titleRef = useRef(null);
    const metadataRef = useRef(null);
    const descriptionRef = useRef(null);
    const pricesRef = useRef(null);

    useEffect(() => {
        let candidate = null;
        let activeTouches = 0;
        let suppressHoldClick = false;
        const cancelHold = () => {
            window.clearTimeout(candidate?.timer);
            candidate = null;
        };
        const start = (event) => {
            const freshContact = activeTouches === 0;
            activeTouches = event.touches.length;
            if (freshContact) suppressHoldClick = false;
            cancelHold();
            if (!freshContact || activeTouches !== 1 || glassPeekOpenRef.current) return;
            const trigger = event.target.closest?.("[data-glassware]");
            const key = trigger?.dataset.glassware;
            const asset = pricesRef.current?.contains(trigger) && Object.hasOwn(GLASSWARE, key) ? GLASSWARE[key] : null;
            if (!asset) return;
            const touch = event.touches[0];
            const pending = { id: touch.identifier, x: touch.clientX, y: touch.clientY };
            pending.timer = window.setTimeout(() => {
                if (candidate !== pending) return;
                candidate = null;
                suppressHoldClick = true;
                glassPeekOpenRef.current = true;
                setPeekAsset(asset);
            }, 500);
            candidate = pending;
        };
        const move = (event) => {
            if (suppressHoldClick) {
                if (event.cancelable) event.preventDefault();
                event.stopPropagation();
                return;
            }
            if (!candidate) return;
            const touch = Array.from(event.touches).find(item => item.identifier === candidate.id);
            if (event.touches.length !== 1 || !touch
                || Math.hypot(touch.clientX - candidate.x, touch.clientY - candidate.y) >= 10) {
                cancelHold();
            }
        };
        const end = (event) => {
            activeTouches = event.touches.length;
            cancelHold();
            // Suppress activation only after a recognized hold.
            if (suppressHoldClick) {
                if (event.cancelable) event.preventDefault();
                event.stopPropagation();
            }
        };
        const cancel = (event) => {
            activeTouches = event.touches.length;
            cancelHold();
            if (suppressHoldClick) event.stopPropagation();
        };
        const click = (event) => {
            if (!suppressHoldClick) return;
            event.preventDefault();
            event.stopImmediatePropagation();
        };
        const pointerDown = (event) => {
            if (event.pointerType === "mouse" && activeTouches === 0) suppressHoldClick = false;
        };
        const passiveCapture = { passive: true, capture: true };
        // Capture observes second contacts anywhere, including outside the card.
        window.addEventListener("touchstart", start, passiveCapture);
        window.addEventListener("touchmove", move, { passive: false, capture: true });
        window.addEventListener("touchend", end, { passive: false, capture: true });
        window.addEventListener("touchcancel", cancel, passiveCapture);
        window.addEventListener("scroll", cancelHold, passiveCapture);
        window.addEventListener("click", click, true);
        window.addEventListener("pointerdown", pointerDown, passiveCapture);
        return () => {
            cancelHold();
            window.removeEventListener("touchstart", start, true);
            window.removeEventListener("touchmove", move, true);
            window.removeEventListener("touchend", end, true);
            window.removeEventListener("touchcancel", cancel, true);
            window.removeEventListener("scroll", cancelHold, true);
            window.removeEventListener("click", click, true);
            window.removeEventListener("pointerdown", pointerDown, true);
        };
    }, []);

    const debugOutline = (color) =>
        spatialDebug
            ? {
                outline: `1px solid ${color}`,
                outlineOffset: "-1px",
            }
            : {};

    const handleDoubleTap = (e) => {

        const now = Date.now();
        const delta = now - lastTap.current;

        console.log("[doubleTap]", {
            delta,
            willToggle: delta < 300,
        });

        if (delta < 300) {

            e.preventDefault();

            setShowArt(prev => {
                const next = !prev;
                console.log("[doubleTap]", {
                    showArt: next,
                });
                return next;
            });
        }

        lastTap.current = now;
    };

    useEffect(() => {
        setBackgroundLoaded(loadedBackgroundUrls.has(beer.beercard_background_url));
    }, [beer.beercard_background_url]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (panelRef.current && !panelRef.current.contains(event.target)) {
                setShowBrewery(false);
            }
        };

        document.addEventListener("mousedown", handleClickOutside);

        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, []);

    useEffect(() => {
        if (!spatialDebug) return;

        const toRect = (node) => {
            if (!node) return null;

            const rect = node.getBoundingClientRect();

            return {
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom),
                height: Math.round(rect.height),
            };
        };

        const logCardLayout = (phase) => {
            const description = descriptionRef.current;
            const titleRect = toRect(titleRef.current);
            const metadataRect = toRect(metadataRef.current);
            const descriptionRect = toRect(description);
            const pricesRect = toRect(pricesRef.current);
            const descriptionStyle = description
                ? window.getComputedStyle(description)
                : null;
            const cardStyle = layoutRef?.current
                ? window.getComputedStyle(layoutRef.current)
                : null;
            const metadataHeight = metadataRect?.height || 0;
            const headerMetaHeight = (titleRect?.height || 0) + metadataHeight;
            const fixedStackHeight =
                headerMetaHeight + (pricesRect?.height || 0);
            const gapMetaToDescription =
                metadataRect && descriptionRect
                    ? Math.round(
                        descriptionRect.top - metadataRect.bottom
                    )
                    : null;
            const gapDescriptionToPrices =
                descriptionRect && pricesRect
                    ? Math.round(pricesRect.top - descriptionRect.bottom)
                    : null;

            console.log("[card-layout]", {
                phase,
                beerId: beer.id,
                cardComputedStyle: cardStyle
                    ? {
                        display: cardStyle.display,
                        flexDirection: cardStyle.flexDirection,
                        justifyContent: cardStyle.justifyContent,
                        alignItems: cardStyle.alignItems,
                        height: cardStyle.height,
                        minHeight: cardStyle.minHeight,
                        overflow: cardStyle.overflow,
                    }
                    : null,
                cardRect: toRect(layoutRef?.current),
                titleRect,
                metadataRect,
                descriptionRect,
                pricesRect,
                verticalGaps: {
                    metaToDescription: gapMetaToDescription,
                    descriptionToPrices: gapDescriptionToPrices,
                },
                regionHeights: {
                    headerMeta: headerMetaHeight,
                    metadata: metadataHeight,
                    description: descriptionRect?.height || null,
                    prices: pricesRect?.height || null,
                    fixedStack: fixedStackHeight,
                },
                descriptionMetrics: description
                    ? {
                        scrollHeight: description.scrollHeight,
                        clientHeight: description.clientHeight,
                        offsetHeight: description.offsetHeight,
                        isClipped:
                            description.scrollHeight > description.clientHeight,
                        computedStyle: descriptionStyle
                            ? {
                                display: descriptionStyle.display,
                                lineHeight: descriptionStyle.lineHeight,
                                fontSize: descriptionStyle.fontSize,
                                flexGrow: descriptionStyle.flexGrow,
                                flexShrink: descriptionStyle.flexShrink,
                                flexBasis: descriptionStyle.flexBasis,
                                minHeight: descriptionStyle.minHeight,
                                height: descriptionStyle.height,
                                maxHeight: descriptionStyle.maxHeight,
                                overflow: descriptionStyle.overflow,
                                marginTop: descriptionStyle.marginTop,
                                marginBottom: descriptionStyle.marginBottom,
                            }
                            : null,
                    }
                    : null,
            });
        };

        logCardLayout("mount");

        const frame = requestAnimationFrame(() => {
            logCardLayout("frame");
        });

        return () => cancelAnimationFrame(frame);
    }, [beer.id, layoutRef, spatialDebug]);


    const rawColor = resolveColor(beer.color);
    const beerColor = adjustColorForUI(rawColor);
    const accentBulletColor = withAlpha(beerColor, 0.58);
    const separatorColor = withAlpha(beerColor, 0.42);

    const colorLabel =
        colorLabelMap[rawColor] || beer.color;

    const breweryLogos = {
        tiburon: "/logos/tiburon.webp",
        invitada: "/logos/invitada.png",
        default: "/logos/default.png"
    };

    const breweryInfo = {
        tiburon: {
            name: "Tiburón Brewing Co.",
            location: "Xalapa, México",
            type: "Artesanal",
            description: "Especialidad en IPAs intensas"
        },
        invitada: {
            name: "Cervecería Invitada",
            location: "México",
            type: "Invitada",
            description: "Selección rotativa"
        },
        default: {
            name: "Cervecería",
            location: "",
            type: "",
            description: ""
        }
    };

    const normalize = (str) =>
        str
            ?.toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");

    const breweryKey = normalize(beer.brewery) || "default";
    const logo = breweryLogos[breweryKey] || breweryLogos.default;
    const brewery = breweryInfo[breweryKey] || breweryInfo.default;

    console.log(
        "CARD RENDER",
        beer.name,
        Math.round(performance.now())
    );

    console.log(
        "BACKGROUND STATE",
        beer.name,
        {
            loaded: backgroundLoaded,
            url: beer.beercard_background_url,
        }
    );

    return (
        <>
        <div
            ref={layoutRef}
            className="beer-card"
            data-atlas-card={beer.id}
            data-beer-name={beer.name}
            onClick={handleDoubleTap}
            style={{
                position: "relative",
                height: "calc(var(--atlas-vh, 100vh) - 140px)",
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-start",
                border: `2px solid ${beerColor}`,
                borderTop: `6px solid ${beerColor}`,
                boxShadow: `0 0 6px ${beerColor}`,
                outline: spatialDebug ? "2px solid rgba(255, 214, 102, 0.95)" : undefined,
                outlineOffset: spatialDebug ? "-2px" : undefined,
            }}
        >
            {beer.beercard_background_url && (
                <img
                    src={beer.beercard_background_url}
                    alt=""
                    aria-hidden="true"
                    draggable={false}
                    onLoad={() => {
                        console.log(
                            "BACKGROUND LOADED",
                            beer.name,
                            performance.now()
                        );

                        loadedBackgroundUrls.add(
                            beer.beercard_background_url
                        );

                        setBackgroundLoaded(true);
                    }}
                    onError={() => setBackgroundLoaded(false)}
                    style={{
                        position: "absolute",
                        inset: 0,
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                        zIndex: 0,
                        opacity: backgroundLoaded ? 1 : 0,
                        transition: "opacity 160ms ease",
                        pointerEvents: "none",
                        userSelect: "none",
                    }}
                />
            )}

            {/* ⭐ FEATURED BADGE */}
            {beer.is_featured && (
                <div
                    style={{
                        position: "absolute",
                        top: "12px",
                        right: "14px",

                        zIndex: 15,

                        fontSize: "28px",

                        opacity: 0.92,

                        textShadow: `
                            0 0 8px rgba(0,0,0,0.7),
                            0 0 12px rgba(255,215,80,0.35),
                            0 0 22px rgba(255,215,80,0.18)
                        `,

                        animation:
                            "featuredCardGlow 5.5s ease-in-out infinite",
                    }}
                >
                    ⭐
                </div>
            )}

            <div
                className="beer-card-header-meta-region"
                style={{
                    position: "relative",
                    flex: "0 0 auto",
                    zIndex: 1,
                    ...debugOutline("rgba(24, 144, 255, 0.45)"),
                }}
            >
                <h2
                    ref={titleRef}
                    style={{
                        margin: "0 0 11px",
                        paddingRight: "42px",
                        lineHeight: 1.15,
                        ...debugOutline("rgba(255, 120, 117, 0.95)"),
                    }}
                >
                    {beer.name}
                </h2>

                <p
                    ref={metadataRef}
                    style={{
                        margin: 0,
                        fontSize: "0.9rem",
                        lineHeight: 1.38,
                        color: "rgba(255,255,255,0.9)",
                        ...debugOutline("rgba(64, 169, 255, 0.95)"),
                    }}
                >
                    <strong>Style:</strong> {beer.style}{" "}
                    <span style={{ color: accentBulletColor }}>•</span>{" "}
                    <strong>ABV:</strong> {formatABV(beer.abv)}
                    {beer.color && (
                        <>
                            {" "}
                            <span style={{ color: accentBulletColor }}>•</span>{" "}
                            <strong>Color:</strong> {colorLabel}
                        </>
                    )}
                </p>

                <div
                    aria-hidden="true"
                    style={{
                        marginTop: "9px",
                        borderTop: `1.5px solid ${separatorColor}`,
                    }}
                />
            </div>

            {beer.description && (
                <p
                    ref={descriptionRef}
                    className="beer-description beer-card-description-region"
                    style={{
                        position: "relative",
                        flex: "0 1 auto",
                        minHeight: 0,
                        marginTop: "12px",
                        marginBottom: 0,
                        lineHeight: 1.48,
                        color: "rgba(255,255,255,0.86)",
                        paddingLeft: "2px",
                        paddingRight: "2px",
                        overflow: "hidden",
                        zIndex: 1,
                        ...debugOutline("rgba(250, 173, 20, 0.95)"),
                    }}
                >
                    {beer.description}
                </p>
            )}

            <div
                ref={pricesRef}
                className="beer-prices beer-card-prices-region"
                style={{
                    position: "relative",
                    flex: "0 0 auto",
                    marginTop: "14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0px",
                    paddingRight: "70px", // Keep prices clear of the absolute brewery logo.
                    zIndex: 1,
                    ...debugOutline("rgba(82, 196, 26, 0.95)"),
                }}
            >
                {beer.prices ? (
                    Object.entries(beer.prices).map(([size, price], index, entries) => {
                        const glass = Object.hasOwn(GLASSWARE, size) ? GLASSWARE[size] : null;
                        const previousKey = entries[index - 1]?.[0];
                        const previousGlass = Object.hasOwn(GLASSWARE, previousKey) ? GLASSWARE[previousKey] : null;
                        if (!glass) {
                            return (
                                <p key={size} style={{ margin: 0 }}>
                                    {size.replace("_", " ")}: ${price}
                                </p>
                            );
                        }
                        return (
                            <div key={size} style={{
                                display: "grid",
                                width: "210px",
                                maxWidth: "100%",
                                alignSelf: "center",
                                gridTemplateColumns: "minmax(0, 1fr) 70px 42px",
                                alignItems: "center",
                                columnGap: "4px",
                                height: "58px",
                                // Preserve the first pair's spacing as the glass sizes increase.
                                marginTop: previousGlass ? Math.max(0, (previousGlass.size + glass.size) / 2 - 58) : 0,
                                fontSize: "14px",
                                lineHeight: 1.2,
                            }}>
                                <span style={{ justifySelf: size === "taster" ? "center" : "start", textAlign: "center", transform: size === "taster" ? "translateX(-9px)" : undefined }}>
                                    <span style={{ display: "block" }}>{glass.label}</span>
                                    <span style={{ display: "block", fontSize: "10px", opacity: 0.6, marginTop: "2px" }}>
                                        {glass.capacity}
                                    </span>
                                </span>
                                <span style={{ position: "relative", width: "70px", height: "58px" }}>
                                    <span
                                        data-glassware={size}
                                        onTouchStart={(event) => {
                                            // Keep the card's hold idle; two-finger gestures still bubble.
                                            if (event.touches.length === 1) event.stopPropagation();
                                        }}
                                        onContextMenu={(event) => event.preventDefault()}
                                        onDragStart={(event) => event.preventDefault()}
                                        style={{
                                            position: "absolute",
                                            left: "50%",
                                            top: "50%",
                                            transform: "translate(-50%, -50%)",
                                            width: glass.size * 0.5 + 4,
                                            height: glass.size * 0.78 + 4,
                                            userSelect: "none",
                                            WebkitUserSelect: "none",
                                            WebkitTouchCallout: "none",
                                        }}
                                    />
                                    <img
                                        src={glass.src}
                                        alt=""
                                        aria-hidden="true"
                                        draggable={false}
                                        style={{
                                            display: "block",
                                            position: "absolute",
                                            left: "50%",
                                            top: "50%",
                                            transform: "translate(-50%, -50%)",
                                            width: glass.size,
                                            height: glass.size,
                                            objectFit: "contain",
                                            pointerEvents: "none",
                                            userSelect: "none",
                                            WebkitUserSelect: "none",
                                            WebkitTouchCallout: "none",
                                        }}
                                    />
                                </span>
                                <span style={{ whiteSpace: "nowrap", textAlign: "right" }}>${price}</span>
                            </div>
                        );
                    })
                ) : (
                    <p style={{ margin: 0 }}>No prices</p>
                )}
            </div>

            <img
                onClick={(e) => {
                    e.stopPropagation();
                    setShowBrewery(prev => !prev);
                }}
                src={logo}
                alt="brewery"
                style={{
                    position: "absolute",
                    bottom: "10px",
                    right: "10px",
                    zIndex: 1,
                    width: "70px",
                    opacity: 0.2,
                    cursor: "pointer",
                    userSelect: "none",
                    filter: "grayscale(100%) contrast(1.2)"
                }}
            />

            <div
                ref={panelRef}
                style={{
                    position: "absolute",
                    bottom: "90px",
                    right: "10px",
                    width: "180px",
                    background: "rgba(0,0,0,0.9)",
                    color: "#fff",
                    padding: "10px",
                    borderRadius: "8px",
                    fontSize: "12px",
                    zIndex: 20,
                    opacity: showBrewery ? 1 : 0,
                    transform: showBrewery
                        ? "translateY(0px)"
                        : "translateY(10px)",
                    pointerEvents: showBrewery ? "auto" : "none",
                    transition: "all 0.2s ease"
                }}
            >
                <strong>{brewery.name}</strong>

                {brewery.location && (
                    <div style={{ opacity: 0.7 }}>
                        {brewery.location}
                    </div>
                )}

                {brewery.type && (
                    <div style={{ marginTop: "4px" }}>
                        {brewery.type}
                    </div>
                )}

                {brewery.description && (
                    <div style={{ opacity: 0.7, marginTop: "6px" }}>
                        {brewery.description}
                    </div>
                )}

                <div
                    style={{
                        marginTop: "8px",
                        textDecoration: "underline",
                        cursor: "pointer"
                    }}
                >
                    Ver más
                </div>
            </div>

        </div>
        {peekAsset && (
            <div
                onClick={(event) => event.stopPropagation()}
                onTouchStart={(event) => event.stopPropagation()}
                onTouchMove={(event) => event.stopPropagation()}
                onTouchEnd={(event) => event.stopPropagation()}
                onTouchCancel={(event) => event.stopPropagation()}
            >
            <PeekOverlay
                label={peekAsset.label}
                onClose={() => {
                    glassPeekOpenRef.current = false;
                    setPeekAsset(null);
                }}
                panelStyle={{ display: "flex", background: "transparent", cursor: "default", pointerEvents: "none" }}
            >
                {/* Ignore transparent PNG margins while keeping the image's rendered size. */}
                <div style={{ position: "absolute", inset: peekAsset.peekInset, pointerEvents: "auto" }}>
                <button
                    type="button"
                    aria-label="Cerrar cristalería"
                    onClick={() => {
                        glassPeekOpenRef.current = false;
                        setPeekAsset(null);
                    }}
                    style={{
                        position: "absolute",
                        top: "-4px",
                        left: "-4px",
                        transform: "translate(-100%, -100%)",
                        width: "48px",
                        height: "48px",
                        padding: 0,
                        border: 0,
                        background: "transparent",
                        color: "rgba(255,255,255,0.95)",
                        fontSize: "36px",
                        lineHeight: 1,
                        cursor: "pointer",
                    }}
                >
                    ×
                </button>
                </div>
                <img
                    src={peekAsset.src}
                    alt={peekAsset.label}
                    draggable={false}
                    style={{
                        display: "block",
                        width: "auto",
                        height: "auto",
                        maxWidth: "min(480px, calc(100vw - 40px))",
                        maxHeight: "calc(100dvh - 40px)",
                        objectFit: "contain",
                        pointerEvents: "none",
                    }}
                />
            </PeekOverlay>
            </div>
        )}
        </>
    );
}
