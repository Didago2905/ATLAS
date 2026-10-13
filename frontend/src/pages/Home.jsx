import { useEffect, useId, useRef, useState, useLayoutEffect } from "react";
import Layout from "../layout/Layout";
import TapListSettings from "../layout/TapListSettings";
import TapGrid from "../components/TapGrid";
import PeekOverlay from "../components/PeekOverlay";
import useCatalogSession from "../catalog/useCatalogSession";
import useTutorialImage from "../tutorial/useTutorialImage";
import { resolveHomeTutorial, readTutorialOutcome, finishTutorial, clearTutorialCheckpoint, isExplicitTutorialStart } from "../tutorial/tutorialLifecycle";
import { useNavigate, useLocation } from "react-router-dom";
import museumIcon from "../assets/icons/museum-leviathan-icon-final.webp";
import tapListIcon from "../assets/icons/tap-list-icon-transparent.webp";
import sortIcon from "../assets/icons/sort-imperial-transparent.webp";
import "./Home.css";

const tritonIntro = "/static/icons/tutorial/triton-intro-taplist.webp";
const tritonFinale = "/static/icons/tutorial/triton-home-finale.webp";

const HOME_ARTWORK = {
    museum: { src: museumIcon, label: "Museo", compactHitbox: true },
    order: { src: sortIcon, label: "Orden", compactHitbox: true },
    tapList: { src: tapListIcon, label: "Tap List" },
};

export default function Home() {

    const navigate = useNavigate(); // 🔥 NUEVO
    const location = useLocation();
    const [tutorialEntry, setTutorialEntry] = useState(() => resolveHomeTutorial(location));
    useEffect(() => {
        if (tutorialEntry === "epilogue") clearTutorialCheckpoint();
    }, [tutorialEntry]);
    const [peekAsset, setPeekAsset] = useState(null);
    const artworkOpenRef = useRef(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const settingsTriggerRef = useRef(null);
    const settingsPanelId = useId();
    const { beers } = useCatalogSession();
    const tutorialPending = tutorialEntry === "welcome";
    const tutorialActive = tutorialPending && beers.length > 0 && !peekAsset;
    const tritonReady = useTutorialImage(tritonIntro, tutorialPending);
    const [tutorialEpiloguePhase, setTutorialEpiloguePhase] = useState("museum-await");
    const tutorialEpilogueActive = tutorialEntry === "epilogue" && tutorialEpiloguePhase !== "completed";
    const tutorialEpilogueAwaiting = ["museum-await", "order-await", "settings-await", "farewell-await"].includes(tutorialEpiloguePhase);
    const tritonFinaleReady = useTutorialImage(tritonFinale, tutorialEpilogueActive);
    const tutorialGridRef = useRef(null);
    const tritonFinaleRef = useRef(null);
    const finaleDialogueRef = useRef(null);
    const tutorialDepartureRef = useRef(null);

    useLayoutEffect(() => {
        if (isExplicitTutorialStart(location)) {
            const entry = resolveHomeTutorial(location);
            setTutorialEntry(entry);
            if (entry === "welcome") setTutorialEpiloguePhase("museum-await");
            const query = new URLSearchParams(location.search);
            query.delete("restart");
            navigate({ pathname: location.pathname, search: query.toString() ? `?${query}` : "", hash: location.hash }, { replace: true, state: null });
        } else if (readTutorialOutcome()) {
            // BeerDetail's departure cleanup may run after Home's initializer.
            setTutorialEntry("normal");
        }
    }, [location.key, navigate]);

    useLayoutEffect(() => {
        tutorialDepartureRef.current = { entry: tutorialEntry, active: tutorialPending || tutorialEpilogueActive };
    });
    useLayoutEffect(() => () => {
        const current = tutorialDepartureRef.current;
        if (!current?.active || readTutorialOutcome() || window.location.pathname === "/") return;
        if (current.entry === "welcome" && window.location.pathname.startsWith("/beer/")) return;
        finishTutorial("omitted");
    }, []);

    useLayoutEffect(() => {
        if (!tutorialEpilogueActive) return;
        const grid = tutorialGridRef.current;
        const measure = () => {
            const top = Math.max(0, grid.getBoundingClientRect().top);
            grid.style.setProperty("--home-epilogue-height", `${Math.max(0, window.innerHeight - top)}px`);
            const image = tritonFinaleRef.current.getBoundingClientRect();
            const stage = tritonFinaleRef.current.parentElement.getBoundingClientRect();
            grid.style.setProperty("--home-epilogue-triton-width", `${image.width}px`);
            grid.style.setProperty("--home-epilogue-dialogue-left", `${Math.max(12, image.left - stage.left)}px`);
            grid.style.setProperty("--home-epilogue-dialogue-top", `${Math.max(12, image.top - stage.top + image.height * 0.18 - finaleDialogueRef.current.offsetHeight - 12)}px`);
        };
        measure();
        window.addEventListener("resize", measure);
        return () => window.removeEventListener("resize", measure);
    }, [tutorialEpilogueActive, beers.length, tritonFinaleReady, tutorialEpiloguePhase]);

    useEffect(() => {
        if (tutorialActive) setSettingsOpen(false);
    }, [tutorialActive]);

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
            if (!freshContact || activeTouches !== 1 || artworkOpenRef.current) return;
            const trigger = event.target.closest?.("[data-home-artwork]");
            const asset = HOME_ARTWORK[trigger?.dataset.homeArtwork];
            if (!asset) return;
            const touch = event.touches[0];
            const pending = { id: touch.identifier, x: touch.clientX, y: touch.clientY };
            pending.timer = window.setTimeout(() => {
                if (candidate !== pending) return;
                candidate = null;
                suppressHoldClick = true;
                artworkOpenRef.current = true;
                setSettingsOpen(false);
                setPeekAsset(asset);
            }, 500);
            candidate = pending;
        };
        const move = (event) => {
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
            // Suppress native select activation only after a recognized hold.
            if (suppressHoldClick && event.cancelable) event.preventDefault();
        };
        const cancel = (event) => {
            activeTouches = event.touches.length;
            cancelHold();
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
        // Capture also observes the transparent select and second contacts outside Home controls.
        window.addEventListener("touchstart", start, passiveCapture);
        window.addEventListener("touchmove", move, passiveCapture);
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

    const [sort, setSort] = useState(() => {
        const saved = localStorage.getItem("tapFilter");
        if (saved) {
            try {
                return JSON.parse(saved).sort || "tap";
            } catch {
                return "tap";
            }
        }
        return "tap";
    });

    return (
        <Layout>
            {({ background, onSelectBackground }) => (
                <>
            <div className="home-controls" inert={tutorialActive || tutorialEpilogueActive ? "" : undefined}>
                <button
                    type="button"
                    className="home-controls__museum"
                    aria-label="Museo"
                    data-home-artwork="museum"
                    onContextMenu={(event) => event.preventDefault()}
                    onDragStart={(event) => event.preventDefault()}
                    onClick={() => navigate("/museum")}
                >
                    <img src={museumIcon} alt="" draggable={false}
                        className={tutorialEpilogueActive && tutorialEpiloguePhase === "museum-await" ? "beerdetail-tutorial-glassware--waiting" : undefined} />
                    <span aria-hidden="true" style={{ height: "15px" }} />
                </button>

                <label
                    className="home-controls__order"
                    data-home-artwork="order"
                    onContextMenu={(event) => event.preventDefault()}
                    onDragStart={(event) => event.preventDefault()}
                >
                    <img src={sortIcon} alt="" draggable={false}
                        className={tutorialEpilogueActive && tutorialEpiloguePhase === "order-await" ? "beerdetail-tutorial-glassware--waiting" : undefined} />
                    <select
                        aria-label="Orden"
                        value={sort}
                        onChange={(e) => setSort(e.target.value)}
                    >
                        <option value="tap">Tap</option>
                        <option value="abv">Alcohol</option>
                        <option value="name">Nombre</option>
                        <option value="style">Estilo</option>
                    </select>
                </label>
            </div>

            <div className="home-settings-anchor" inert={tutorialActive || tutorialEpilogueActive ? "" : undefined}>
                <button
                    type="button"
                    className="home-settings-trigger"
                    ref={settingsTriggerRef}
                    aria-label="Configuración de Tap List"
                    aria-expanded={settingsOpen}
                    aria-controls={settingsOpen ? settingsPanelId : undefined}
                    data-home-artwork="tapList"
                    onClick={() => setSettingsOpen(open => !open)}
                    onContextMenu={(event) => event.preventDefault()}
                    onDragStart={(event) => event.preventDefault()}
                >
                    <img
                        className={`home-catalog-icon${tutorialEpilogueActive && tutorialEpiloguePhase === "settings-await" ? " beerdetail-tutorial-glassware--waiting" : ""}`}
                        src={tapListIcon}
                        alt="Tap List"
                        draggable={false}
                    />
                </button>
                <TapListSettings
                    background={background}
                    onSelect={onSelectBackground}
                    open={settingsOpen && !tutorialActive}
                    onOpenChange={setSettingsOpen}
                    triggerRef={settingsTriggerRef}
                    panelId={settingsPanelId}
                    onRestartTutorial={() => {
                        const query = new URLSearchParams(location.search);
                        query.set("tutorial", "1");
                        query.set("restart", "1");
                        navigate({ pathname: "/", search: `?${query}`, hash: location.hash }, { replace: true, state: null });
                    }}
                />
            </div>

            {/* 🍺 TAP GRID */}
            <div ref={tutorialGridRef} className={tutorialEpilogueActive ? "home-tutorial-epilogue-grid" : tutorialActive ? "home-tutorial-grid" : undefined}>
                <div inert={tutorialEpilogueActive ? "" : undefined} style={{ display: tutorialEpilogueActive ? "block" : "contents" }}>
                <TapGrid
                    sort={sort}
                    tutorialStep={tutorialActive ? "beerdetail-intro" : undefined}
                />
                </div>
                {tutorialEpilogueActive && (
                    <div className={`home-tutorial-epilogue-layer${tutorialEpiloguePhase === "farewell-closing" ? " home-tutorial-epilogue-layer--closing" : ""}`}
                        onTransitionEnd={event => {
                            if (event.target === event.currentTarget && event.propertyName === "opacity") {
                                setTutorialEpiloguePhase(phase => phase === "farewell-closing" ? "completed" : phase);
                            }
                        }}>
                        <div className="home-tutorial-epilogue-stage">
                            <img ref={tritonFinaleRef} className="home-tutorial-epilogue-triton" src={tritonFinale}
                                style={{ visibility: tritonFinaleReady ? "visible" : "hidden" }}
                                alt="" draggable={false} />
                            <aside ref={finaleDialogueRef}
                                className={`home-tutorial-dialogue home-tutorial-epilogue-dialogue${tutorialEpilogueAwaiting ? " beerdetail-tutorial-dialogue--waiting" : ""}`}
                                style={{ visibility: tritonFinaleReady ? "visible" : "hidden" }} aria-live="polite">
                                <span className="beerdetail-dialogue-corner beerdetail-dialogue-corner--tl" aria-hidden="true" />
                                <span className="beerdetail-dialogue-corner beerdetail-dialogue-corner--tr" aria-hidden="true" />
                                <span className="beerdetail-dialogue-corner beerdetail-dialogue-corner--bl" aria-hidden="true" />
                                <span className="beerdetail-dialogue-corner beerdetail-dialogue-corner--br" aria-hidden="true" />
                                {tutorialEpiloguePhase === "order-await" ? <>
                                    <p><strong>¿Buscas algo en particular?</strong></p>
                                    <p>¡La Orden Imperial te ayuda a organizar las cervezas por su posición en el Tap, volumen de alcohol, nombre o estilo!</p>
                                </> : tutorialEpiloguePhase === "settings-await" ? <>
                                    <p><strong>¡Ah, casi lo olvido!</strong></p>
                                    <p>Si necesitas cambiar algo, toca el logo de Tiburón en el Tap List. ¡Ahí escondimos los ajustes!</p>
                                </> : ["farewell-await", "farewell-closing"].includes(tutorialEpiloguePhase) ? <>
                                    <p><strong>¡Y eso es todo por ahora!</strong><br />Ya conoces los secretos básicos<br />de nuestro reino.</p>
                                    <p><strong>¡Pero aún queda mucho por descubrir!</strong><br />Explora a tu ritmo y recuerda…</p>
                                    <p><strong>¡Nos vemos en las profundidades! 🦈</strong></p>
                                </> : <>
                                    <p><strong>¡Y aquí tenemos nuestro Museo!</strong></p>
                                    <p>Un espacio para descubrir el arte de Tiburón. ¡Date una vuelta cuando quieras!</p>
                                </>}
                            </aside>
                        </div>
                    </div>
                )}
            </div>

            {tutorialEpilogueActive && <div aria-hidden="true"
                style={{ position: "fixed", inset: 0, zIndex: 203, background: "transparent" }}
                onTouchStart={event => event.stopPropagation()}
                onTouchMove={event => event.stopPropagation()}
                onTouchEnd={event => event.stopPropagation()}
                onTouchCancel={event => event.stopPropagation()}
                onPointerDown={event => event.stopPropagation()}
                onClick={event => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (tritonFinaleReady && tutorialEpiloguePhase === "farewell-await") {
                        finishTutorial("completed");
                        setTutorialEpiloguePhase(window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "completed" : "farewell-closing");
                        return;
                    }
                    if (tritonFinaleReady) setTutorialEpiloguePhase(phase => ({
                        "museum-await": "order-await",
                        "order-await": "settings-await",
                        "settings-await": "farewell-await",
                    }[phase] || phase));
                }} />}

            {tutorialActive && (
                <>
                    <div className="home-tutorial-shade" aria-hidden="true" />
                    <aside className="home-tutorial-message" aria-live="polite">
                        <div className="home-tutorial-intro-character">
                        <img
                            className="home-tutorial-triton"
                            src={tritonIntro}
                            style={{ visibility: tritonReady ? "visible" : "hidden" }}
                            alt=""
                            draggable={false}
                        />
                        <button type="button" className="home-tutorial-skip"
                            onPointerDown={event => event.stopPropagation()}
                            onTouchStart={event => event.stopPropagation()}
                            onTouchEnd={event => event.stopPropagation()}
                            onClick={event => {
                                event.preventDefault();
                                event.stopPropagation();
                                finishTutorial("omitted");
                                setTutorialEntry("normal");
                            }}>Omitir tutorial</button>
                        </div>
                        <div className="home-tutorial-dialogue">
                            <p className="home-tutorial-greeting"><strong>¡Bienvenido a Tiburón!</strong></p>
                            <p>Aquí encontrarás lo que estamos sirviendo hoy.</p>
                            <p><strong>¿Cuál se te antoja?</strong>{" "}
                                Toca una cerveza para conocerla.</p>
                        </div>
                    </aside>
                </>
            )}

            {peekAsset && (
                <PeekOverlay
                    data-atlas-artwork-peek
                    label={peekAsset.label}
                    onClose={() => {
                        artworkOpenRef.current = false;
                        setPeekAsset(null);
                    }}
                    panelStyle={{
                        display: "flex",
                        background: "transparent",
                        pointerEvents: peekAsset.compactHitbox ? "none" : undefined,
                    }}
                >
                    {peekAsset.compactHitbox && (
                        <div className="home-artwork-peek-hitbox" />
                    )}
                    <img
                        className="home-artwork-peek-image"
                        src={peekAsset.src}
                        alt={peekAsset.label}
                        draggable={false}
                    />
                </PeekOverlay>
            )}

                </>
            )}
        </Layout>
    );
}
