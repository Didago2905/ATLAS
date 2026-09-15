import { useEffect, useId, useRef, useState } from "react";
import { TAP_BACKGROUNDS } from "../backgrounds";

export default function TapListSettings({ background, onSelect }) {
    const [open, setOpen] = useState(false);
    const controlRef = useRef(null);
    const triggerRef = useRef(null);
    const panelId = useId();

    useEffect(() => {
        if (!open) return;
        controlRef.current.querySelector('[aria-pressed="true"]')?.focus();
        function onPointerDown(event) {
            if (!controlRef.current?.contains(event.target)) setOpen(false);
        }
        function onKeyDown(event) {
            if (event.key === "Escape") {
                setOpen(false);
                triggerRef.current?.focus();
            }
        }
        document.addEventListener("pointerdown", onPointerDown);
        document.addEventListener("keydown", onKeyDown);
        return () => {
            document.removeEventListener("pointerdown", onPointerDown);
            document.removeEventListener("keydown", onKeyDown);
        };
    }, [open]);

    return (
        <div className="tap-list-settings" ref={controlRef}
            onBlur={event => {
                if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
            }}>
            <button type="button" className="tap-list-settings__trigger"
                ref={triggerRef} aria-label="Configuración de Tap List"
                aria-expanded={open} aria-controls={open ? panelId : undefined}
                onClick={() => setOpen(value => !value)}>
                <span aria-hidden="true">⚙</span>
            </button>
            {open && (
                <section id={panelId} className="tap-list-settings__panel" aria-label="Apariencia">
                    <h2>Apariencia</h2>
                    <div className="tap-list-settings__swatches">
                        {TAP_BACKGROUNDS.map(preset => (
                            <button key={preset.id} type="button"
                                aria-label={preset.label} title={preset.label}
                                aria-pressed={background.id === preset.id}
                                onClick={() => {
                                    onSelect(preset);
                                    setOpen(false);
                                    triggerRef.current?.focus();
                                }}>
                                <span style={{ background: preset.value }} />
                            </button>
                        ))}
                    </div>
                </section>
            )}
        </div>
    );
}
