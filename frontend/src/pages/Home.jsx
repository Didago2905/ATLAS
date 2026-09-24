import { useEffect, useId, useRef, useState } from "react";
import Layout from "../layout/Layout";
import TapListSettings from "../layout/TapListSettings";
import TapGrid from "../components/TapGrid";
import PeekOverlay from "../components/PeekOverlay";
import { useNavigate } from "react-router-dom";
import museumIcon from "../assets/icons/museum-leviathan-icon-final.png";
import tapListIcon from "../assets/icons/tap-list-icon-transparent.png";
import sortIcon from "../assets/icons/sort-imperial-transparent.png";
import "./Home.css";

const HOME_ARTWORK = {
    museum: { src: museumIcon, label: "Museo" },
    order: { src: sortIcon, label: "Orden" },
    tapList: { src: tapListIcon, label: "Tap List" },
};

export default function Home() {

    const navigate = useNavigate(); // 🔥 NUEVO
    const [peekAsset, setPeekAsset] = useState(null);
    const artworkOpenRef = useRef(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const settingsTriggerRef = useRef(null);
    const settingsPanelId = useId();

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
            <div className="home-controls">
                <button
                    type="button"
                    className="home-controls__museum"
                    aria-label="Museo"
                    data-home-artwork="museum"
                    onContextMenu={(event) => event.preventDefault()}
                    onDragStart={(event) => event.preventDefault()}
                    onClick={() => navigate("/museum")}
                >
                    <img src={museumIcon} alt="" draggable={false} />
                    <span aria-hidden="true" style={{ height: "15px" }} />
                </button>

                <label
                    className="home-controls__order"
                    data-home-artwork="order"
                    onContextMenu={(event) => event.preventDefault()}
                    onDragStart={(event) => event.preventDefault()}
                >
                    <img src={sortIcon} alt="" draggable={false} />
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

            <div className="home-settings-anchor">
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
                        className="home-catalog-icon"
                        src={tapListIcon}
                        alt="Tap List"
                        draggable={false}
                    />
                </button>
                <TapListSettings
                    background={background}
                    onSelect={onSelectBackground}
                    open={settingsOpen}
                    onOpenChange={setSettingsOpen}
                    triggerRef={settingsTriggerRef}
                    panelId={settingsPanelId}
                />
            </div>

            {/* 🍺 TAP GRID */}
            <TapGrid sort={sort} />

            {peekAsset && (
                <PeekOverlay
                    data-atlas-artwork-peek
                    label={peekAsset.label}
                    onClose={() => {
                        artworkOpenRef.current = false;
                        setPeekAsset(null);
                    }}
                    panelStyle={{ display: "flex", background: "transparent" }}
                >
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
