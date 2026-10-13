import { useEffect, useRef, useState } from "react";
import { TAP_BACKGROUNDS } from "../backgrounds";

export default function TapListSettings({ background, onSelect, open, onOpenChange, triggerRef, panelId, onRestartTutorial }) {
    const panelRef = useRef(null);
    const [panelView, setPanelView] = useState("main");
    const showTips = panelView === "tips";
    const showDetails = panelView !== "main";
    const tipsBackRef = useRef(null);
    const tipsWereOpenRef = useRef(false);

    useEffect(() => {
        if (!open) {
            tipsWereOpenRef.current = false;
            setPanelView("main");
            return;
        }
        if (showDetails) tipsBackRef.current?.focus({ preventScroll: true });
        else if (tipsWereOpenRef.current) panelRef.current.querySelector('[aria-pressed="true"]')?.focus({ preventScroll: true });
        tipsWereOpenRef.current = showDetails;
    }, [open, showDetails]);

    useEffect(() => {
        if (!open) return;
        panelRef.current.querySelector('[aria-pressed="true"]')?.focus({ preventScroll: true });
        function onPointerDown(event) {
            if (!panelRef.current?.contains(event.target)
                && !triggerRef.current?.contains(event.target)) onOpenChange(false);
        }
        function onKeyDown(event) {
            if (event.key === "Escape") {
                onOpenChange(false);
                triggerRef.current?.focus({ preventScroll: true });
            }
        }
        document.addEventListener("pointerdown", onPointerDown);
        document.addEventListener("keydown", onKeyDown);
        return () => {
            document.removeEventListener("pointerdown", onPointerDown);
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [open, onOpenChange, triggerRef]);

    if (!open) return null;

    return (
        <section id={panelId} className={`tap-list-settings__panel${showDetails ? " tap-list-settings__panel--tips" : ""}`} aria-label="Ajustes"
            ref={panelRef}
            onBlur={event => {
                if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)
                    && !triggerRef.current?.contains(event.relatedTarget)) onOpenChange(false);
            }}>
            {showDetails ? <div className="tap-list-settings__tips">
                <button ref={tipsBackRef} className="tap-list-settings__action" type="button" onClick={() => setPanelView("main")}>← Ajustes</button>
                {showTips ? <>
                <h2>Vistas del Tap List</h2>
                <p>Toca dos veces con dos dedos para alternar entre Focus y Galería.</p>
                <h2>Artwork Peek</h2>
                <p>Mantén presionados los iconos de Museo, Orden Imperial o Tap List para descubrir sus ilustraciones.</p>
                <h2>Peek de cervezas</h2>
                <p>En el modo Galería del Tap List, mantén presionada una cerveza para explorar su vista previa.</p>
                </> : <>
                    <h2>DISEÑO GRÁFICO</h2>
                    <p>Octavio Garnica<br />
                        <a href="https://www.instagram.com/digar_ilustracion/" target="_blank" rel="noopener noreferrer">Instagram: @digar_ilustracion</a>
                    </p>
                    <h2>DESARROLLO</h2>
                    <p>Diego Ortiz<br />
                        <a href="mailto:gypsycat2905@gmail.com">Correo: gypsycat2905@gmail.com</a>
                    </p>
                </>}
            </div> : <>
            <section className="tap-list-settings__quadrant">
                <h2>Tutorial</h2>
                <button className="tap-list-settings__action" type="button" disabled={!onRestartTutorial}
                    onClick={() => {
                        onOpenChange(false);
                        onRestartTutorial?.();
                    }}>Repetir tutorial</button>
                <button className="tap-list-settings__action" type="button" onClick={() => setPanelView("tips")}>Consejos</button>
            </section>
            <section className="tap-list-settings__quadrant">
            <h2>Apariencia</h2>
            <div className="tap-list-settings__swatches">
                {TAP_BACKGROUNDS.map(preset => (
                    <button key={preset.id} type="button"
                        aria-label={preset.label} title={preset.label}
                        aria-pressed={background.id === preset.id}
                        onClick={() => {
                            onSelect(preset);
                            onOpenChange(false);
                            triggerRef.current?.focus({ preventScroll: true });
                        }}>
                        <span style={{ background: preset.value }} />
                    </button>
                ))}
            </div>
            </section>
            <section className="tap-list-settings__quadrant">
                <button className="tap-list-settings__action tap-list-settings__credits-action" type="button" onClick={() => setPanelView("credits")}>Créditos</button>
            </section>
            <div className="tap-list-settings__quadrant" aria-hidden="true" />
            </>}
        </section>
    );
}
