import { useEffect, useRef } from "react";
import { TAP_BACKGROUNDS } from "../backgrounds";

export default function TapListSettings({ background, onSelect, open, onOpenChange, triggerRef, panelId }) {
    const panelRef = useRef(null);

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
        <section id={panelId} className="tap-list-settings__panel" aria-label="Apariencia"
            ref={panelRef}
            onBlur={event => {
                if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)
                    && !triggerRef.current?.contains(event.relatedTarget)) onOpenChange(false);
            }}>
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
    );
}
