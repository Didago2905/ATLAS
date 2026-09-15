import { useState, useEffect, useRef } from "react";
import useCatalogSession from "../catalog/useCatalogSession";
import { useNavigate } from "react-router-dom";
import { audit } from "../utils/audit";
import { createTapTimingLab } from "../diagnostics/tapTimingLab";
import TapTimingLabPanel from "../diagnostics/TapTimingLabPanel";

export default function TapGrid({ sort }) {
    const { beers } = useCatalogSession();

    const navigate = useNavigate();
    const [exiting, setExiting] = useState(false);
    const multitouchGuardRef = useRef(false);
    const multitouchGuardTimerRef = useRef(null);

    const [mobileGridMode, setMobileGridMode] = useState(() => {
        return localStorage.getItem("tap_grid_mode") || "focus";
    });
    const mobileGridModeRef = useRef(mobileGridMode);
    const tapTimingLabEnabled = window.location.pathname === "/"
        && new URLSearchParams(window.location.search).get("tapTimingLab") === "1";
    const [tapTimingLab] = useState(() =>
        tapTimingLabEnabled ? createTapTimingLab() : null
    );

    useEffect(() => {
        if (!tapTimingLabEnabled) return undefined;
        window.ATLAS_TAP_TIMING_LAB = tapTimingLab;
        return () => {
            if (window.ATLAS_TAP_TIMING_LAB === tapTimingLab) {
                delete window.ATLAS_TAP_TIMING_LAB;
            }
        };
    }, [tapTimingLabEnabled, tapTimingLab]);

    console.log("GRID MODE:", mobileGridMode);

    // resto del archivo SIN CAMBIOS

    useEffect(() => {
        if (sort) {
            localStorage.setItem(
                "tapFilter",
                JSON.stringify({ sort })
            );
        }
    }, [sort]);

    useEffect(() => {

        localStorage.setItem(
            "tap_grid_mode",
            mobileGridMode
        );

    }, [mobileGridMode]);

    useEffect(() => {
        localStorage.setItem(
            "tap_grid_mode",
            mobileGridMode
        );
    }, [mobileGridMode]);

    // 🔥 ORDEN
    const sortedBeers = [...beers].sort((a, b) => {
        if (sort === "abv") return (b.abv || 0) - (a.abv || 0);
        if (sort === "name") return a.name.localeCompare(b.name);
        if (sort === "style") return a.style.localeCompare(b.style);
        if (a.is_featured && !b.is_featured) return -1;
        if (!a.is_featured && b.is_featured) return 1;

        return (a.tap_position || 999) - (b.tap_position || 999);
    });

    // 🔥 TAP FIJO (16)
    const maxSlots = 16;
    const tapBeers = sortedBeers.slice(0, maxSlots);

    const filledBeers = [...tapBeers];
    while (filledBeers.length < maxSlots) {
        filledBeers.push(null);
    }

    const shouldShakeFeatured = (beer) => {

        if (!beer.is_featured) return false;

        const key = `seen_featured_${beer.id}_${beer.featured_updated_at}`;

        return !localStorage.getItem(key);
    };

    useEffect(() => {

        let lastTouchTime = 0;
        let lastPhysicalChordIdentifiers = null;

        const normalizeTouchIdentifiers = touches =>
            Array.from(touches, touch => touch.identifier).sort((a, b) => a - b);

        const haveSameIdentifiers = (left, right) =>
            left !== null
            && left.length === right.length
            && left.every((identifier, index) => identifier === right[index]);

        const clearMultitouchGuard = () => {
            multitouchGuardRef.current = false;
            multitouchGuardTimerRef.current = null;
        };

        const armGuardCleanup = () => {
            window.clearTimeout(multitouchGuardTimerRef.current);
            multitouchGuardTimerRef.current = window.setTimeout(
                clearMultitouchGuard,
                350
            );
        };

        const handleTouchStart = (e) => {

            const rawEventSequence = tapTimingLab?.recordTouchStart(e);

            if (e.touches.length >= 2) {
                window.clearTimeout(multitouchGuardTimerRef.current);
                multitouchGuardTimerRef.current = null;
                multitouchGuardRef.current = true;
            }

            // 🔥 solo 2 dedos
            if (e.touches.length !== 2) return;

            const normalizedIdentifiers = normalizeTouchIdentifiers(e.touches);
            const samePhysicalChord = haveSameIdentifiers(
                lastPhysicalChordIdentifiers,
                normalizedIdentifiers
            );

            tapTimingLab?.recordPhysicalChord({
                classification: samePhysicalChord
                    ? "SAME_PHYSICAL_CHORD"
                    : "NEW_PHYSICAL_CHORD",
                identifiers: normalizedIdentifiers,
                rawEventSequence,
            });

            if (samePhysicalChord) return;

            lastPhysicalChordIdentifiers = normalizedIdentifiers;
            const now = Date.now();
            const previousLastTouchTime = lastTouchTime;
            const delta = now - previousLastTouchTime;
            const recognized = delta < 350;
            const modeBefore = mobileGridModeRef.current;

            // 🔥 doble tap rápido
            if (recognized) {

                setMobileGridMode(prev =>
                    prev === "focus"
                        ? "gallery"
                        : "focus"
                );
                mobileGridModeRef.current = modeBefore === "focus" ? "gallery" : "focus";
            }

            lastTouchTime = now;
            tapTimingLab?.recordProductiveDecision({
                recognized,
                deltaMs: delta,
                lastTouchTimeBefore: previousLastTouchTime,
                lastTouchTimeAfter: lastTouchTime,
                thresholdMs: 350,
                modeBefore,
                modeAfter: recognized ? mobileGridModeRef.current : modeBefore,
                rawEventSequence,
            });
        };

        const handleTouchEnd = (e) => {
            tapTimingLab?.recordTouchEnd(e);
            if (lastPhysicalChordIdentifiers !== null) {
                const activeIdentifiers = new Set(
                    Array.from(e.touches, touch => touch.identifier)
                );
                const chordStillActive = lastPhysicalChordIdentifiers.every(
                    identifier => activeIdentifiers.has(identifier)
                );
                if (!chordStillActive) lastPhysicalChordIdentifiers = null;
            }
            if (multitouchGuardRef.current && e.touches.length === 0) {
                armGuardCleanup();
            }
        };

        const handleTouchCancel = (e) => {
            tapTimingLab?.recordCancel(e);
            lastPhysicalChordIdentifiers = null;
            window.clearTimeout(multitouchGuardTimerRef.current);
            clearMultitouchGuard();
        };

        window.addEventListener(
            "touchstart",
            handleTouchStart,
            { passive: true }
        );
        window.addEventListener("touchend", handleTouchEnd, { passive: true });
        window.addEventListener("touchcancel", handleTouchCancel, { passive: true });

        return () => {
            window.removeEventListener(
                "touchstart",
                handleTouchStart
            );
            window.removeEventListener("touchend", handleTouchEnd);
            window.removeEventListener("touchcancel", handleTouchCancel);
            window.clearTimeout(multitouchGuardTimerRef.current);
        };

    }, [tapTimingLab]);

    const isLoading = beers.length === 0;

    return (
        <>
            {tapTimingLab && <TapTimingLabPanel lab={tapTimingLab} />}
            <div
                style={{
                    position: "relative",
                    padding: "20px",

                    opacity: exiting ? 0 : 1,
                    transform: exiting ? "scale(0.96)" : "scale(1)",
                    transition: "all 0.28s cubic-bezier(0.22, 1, 0.36, 1)",
                }}
            >

                {/* GRID TAP */}
                <div
                    style={{
                        display: "grid",
                        gridTemplateColumns:
                            window.innerWidth < 600
                                ? mobileGridMode === "gallery"
                                    ? "repeat(3, 1fr)"
                                    : "repeat(2, 1fr)"
                                : window.innerWidth < 900
                                    ? "repeat(3, 1fr)"
                                    : "repeat(4, 1fr)",
                        gap: "12px",
                        width: "100%",
                    }}
                >
                    {isLoading
                        ? Array.from({ length: 16 }).map((_, index) => (
                            <div
                                key={`skeleton-${index}`}
                                style={{
                                    aspectRatio: "3/4",
                                    borderRadius: "12px",
                                    background: "linear-gradient(90deg, #222, #333, #222)",
                                    backgroundSize: "200% 100%",
                                    animation: "shimmer 1.5s infinite",
                                }}
                            />
                        ))
                        : filledBeers.map((beer, index) => {

                            // 🔥 SLOT VACÍO
                            if (!beer) {
                                return (
                                    <div
                                        key={index}
                                        style={{
                                            aspectRatio: "3/4",
                                            borderRadius: "12px",
                                            background: "rgba(255,255,255,0.05)",
                                            border: "1px dashed rgba(255,255,255,0.1)",
                                        }}
                                    />
                                );
                            }

                            // 🔥 SLOT CON CERVEZA
                            return (
                                <div
                                    key={`${beer.id}-${index}`}
                                    data-atlas-tap-card={beer.id}
                                    onClick={(event) => {

                                        if (multitouchGuardRef.current) {
                                            event.preventDefault();
                                            event.stopPropagation();
                                            return;
                                        }

                                        if (beer.is_featured) {

                                            const key =
                                                `seen_featured_${beer.id}_${beer.featured_updated_at}`;

                                            localStorage.setItem(key, "true");
                                        }

                                        setExiting(true);

                                        setExiting(true);

                                        audit("open_beer", beer.id);

                                        setTimeout(() => {
                                            navigate(`/beer/${beer.id}`, {
                                                state: {
                                                    beers: tapBeers,
                                                    currentIndex: index
                                                }
                                            });
                                        }, 280);
                                    }}
                                    style={{
                                        position: "relative",
                                        aspectRatio: "3/4",
                                        borderRadius: "12px",
                                        overflow: "hidden",
                                        cursor: "pointer",
                                        display: "flex",
                                        flexDirection: "column",
                                        justifyContent: "flex-end",
                                        background: beer.image_url ? "transparent" : "var(--taplist-background, #111)",
                                        boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                                        transition: "transform 0.2s ease",
                                        animation: shouldShakeFeatured(beer)
                                            ? "featuredShake 4s ease-in-out infinite"
                                            : "none",

                                        transformOrigin: "center center",
                                    }}
                                    onMouseEnter={(e) =>
                                        (e.currentTarget.style.transform = "scale(1.03)")
                                    }
                                    onMouseLeave={(e) =>
                                        (e.currentTarget.style.transform = "scale(1)")
                                    }
                                >

                                    {/* ⭐ FEATURED */}
                                    {beer.is_featured && (
                                        <div
                                            style={{
                                                position: "absolute",
                                                top: "-5px",
                                                left: "-2px",
                                                zIndex: 10,
                                                fontSize: "24px",
                                                opacity: 0.95,
                                                textShadow: `
                                            0 0 6px rgba(0,0,0,0.7),
                                            0 0 10px rgba(255,215,80,0.45),
                                            0 0 18px rgba(255,215,80,0.22)
                                             `,
                                                pointerEvents: "none",
                                                animation: shouldShakeFeatured(beer)
                                                    ? "featuredDrop 0.9s cubic-bezier(0.22, 1, 0.36, 1) 0.65s both"
                                                    : "none",
                                            }}
                                        >
                                            ⭐
                                        </div>
                                    )}

                                    {/* 🔥 IMAGEN LAZY + FADE */}
                                    {beer.image_url && (
                                        <img
                                            src={beer.image_url}
                                            alt={beer.name}
                                            loading="lazy"
                                            style={{
                                                position: "absolute",
                                                top: 0,
                                                left: 0,
                                                width: "100%",
                                                height: "100%",
                                                objectFit: "cover",
                                                objectPosition: "center 15%",
                                                opacity: 0,
                                                transition: "opacity 0.4s ease",
                                            }}
                                            onLoad={(e) => {
                                                e.target.style.opacity = 1;
                                            }}
                                        />
                                    )}

                                    {/* INFO SI NO HAY IMAGEN */}
                                    {!beer.image_url && (
                                        <div
                                            style={{
                                                padding: "10px",
                                                background: "rgba(0,0,0,0.6)",
                                                color: "#fff",
                                                fontSize: "14px",
                                            }}
                                        >
                                            <strong>{beer.name}</strong>
                                            <div style={{ opacity: 0.7 }}>{beer.style}</div>
                                            <div style={{ fontSize: "12px", opacity: 0.6 }}>
                                                {beer.abv}% ABV
                                            </div>
                                        </div>
                                    )}

                                </div>
                            );
                        })}
                </div>

            </div>

        </>
    );
}
