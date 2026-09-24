import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export default function PeekOverlay({ children, label, onClose, panelStyle, ...overlayProps }) {
    const backdropPressRef = useRef(false);
    const panelRef = useRef(null);
    const backdropRef = useRef(null);
    const suppressClickRef = useRef(false);
    const transitionActiveRef = useRef(false);
    const onCloseRef = useRef(onClose);

    useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

    useEffect(() => {
        const panel = panelRef.current;
        const backdrop = backdropRef.current;
        let gesture = null;
        let transitionTimer = null;
        let transitionEnd = null;
        const clearTransition = () => {
            window.clearTimeout(transitionTimer);
            if (transitionEnd) panel.removeEventListener("transitionend", transitionEnd);
            transitionTimer = null;
            transitionEnd = null;
        };
        const setVisual = (x, y, scale, opacity) => {
            panel.style.transform = `translate3d(${x}px, ${y}px, 0) scale(${scale})`;
            backdrop.style.opacity = String(opacity);
        };
        const animate = (duration, x, y, scale, opacity, complete) => {
            clearTransition();
            transitionActiveRef.current = true;
            const easing = "cubic-bezier(0.22, 1, 0.36, 1)";
            panel.style.transition = `transform ${duration}ms ${easing}`;
            backdrop.style.transition = `opacity ${duration}ms ${easing}`;
            const finish = () => {
                clearTransition();
                panel.style.transition = "";
                backdrop.style.transition = "";
                transitionActiveRef.current = false;
                complete?.();
            };
            transitionEnd = (event) => {
                if (event.target === panel && event.propertyName === "transform") finish();
            };
            panel.addEventListener("transitionend", transitionEnd);
            transitionTimer = window.setTimeout(finish, duration + 80);
            setVisual(x, y, scale, opacity);
        };
        const restore = () => {
            const wasDragging = gesture?.dragging;
            gesture = null;
            if (wasDragging) animate(250, 0, 0, 0.95, 1);
        };
        const start = (event) => {
            if (transitionActiveRef.current) return;
            restore();
            if (transitionActiveRef.current) return;
            suppressClickRef.current = false;
            if (event.touches.length !== 1) return;
            // Leave controls, images and any scrollable content to their own interactions.
            if (event.target.closest("button, a, input, select, textarea, img, [role='button']")) return;
            for (let node = event.target; node && panel.contains(node); node = node.parentElement) {
                const style = window.getComputedStyle(node);
                if (style.cursor === "pointer") return;
                if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) return;
            }
            const touch = event.touches[0];
            gesture = { id: touch.identifier, x: touch.clientX, y: touch.clientY, dragging: false };
        };
        const cancelMultitouch = (event) => {
            if (event.touches.length > 1) restore();
        };
        const move = (event) => {
            if (!gesture) return;
            const touch = Array.from(event.touches).find(item => item.identifier === gesture.id);
            if (event.touches.length !== 1 || !touch) {
                restore();
                return;
            }
            const dx = touch.clientX - gesture.x;
            const dy = touch.clientY - gesture.y;
            if (!gesture.dragging) {
                if (Math.hypot(dx, dy) < 10) return;
                suppressClickRef.current = true;
                gesture.dragging = true;
            }
            // Claim only a confirmed drag, never the initial touch or a tap.
            if (!event.cancelable) {
                restore();
                return;
            }
            event.preventDefault();
            const horizontal = Math.abs(dx) > Math.abs(dy);
            const distance = Math.abs(horizontal ? dx : dy);
            const visibleSize = horizontal
                ? window.visualViewport?.width || window.innerWidth
                : window.visualViewport?.height || window.innerHeight;
            const threshold = Math.min(150, Math.max(75, visibleSize * 0.17));
            const progress = Math.min(1, distance / threshold);
            const scaleProgress = Math.min(1, distance / (threshold * 1.35));
            setVisual(dx, dy, 0.95 * (1 - 0.10 * scaleProgress), (0.97 - 0.4 * progress) / 0.97);
        };
        const end = (event) => {
            if (!gesture) return;
            // Prevent a completed drag from generating a click after the portal unmounts.
            if (gesture.dragging && event.cancelable) event.preventDefault();
            const touch = Array.from(event.changedTouches).find(item => item.identifier === gesture.id);
            const dx = touch ? touch.clientX - gesture.x : 0;
            const dy = touch ? touch.clientY - gesture.y : 0;
            const horizontal = Math.abs(dx) > Math.abs(dy);
            const displacement = horizontal ? dx : dy;
            const visibleSize = horizontal
                ? window.visualViewport?.width || window.innerWidth
                : window.visualViewport?.height || window.innerHeight;
            const threshold = Math.min(150, Math.max(75, visibleSize * 0.17));
            const dismiss = gesture.dragging && touch
                && Math.abs(displacement) >= threshold;
            if (dismiss) {
                const target = Math.sign(displacement) * Math.max(Math.abs(displacement) + 120, visibleSize * 0.55);
                gesture = null;
                animate(220, horizontal ? target : dx, horizontal ? dy : target, 0.855, 0, () => onCloseRef.current());
            } else {
                restore();
            }
        };
        panel.addEventListener("touchstart", start, { passive: true });
        panel.addEventListener("touchmove", move, { passive: false });
        panel.addEventListener("touchend", end, { passive: false });
        panel.addEventListener("touchcancel", restore, { passive: true });
        window.addEventListener("touchstart", cancelMultitouch, { passive: true, capture: true });
        return () => {
            clearTransition();
            transitionActiveRef.current = false;
            panel.removeEventListener("touchstart", start);
            panel.removeEventListener("touchmove", move);
            panel.removeEventListener("touchend", end);
            panel.removeEventListener("touchcancel", restore);
            window.removeEventListener("touchstart", cancelMultitouch, true);
        };
    }, []);

    return createPortal(
        <div
            {...overlayProps}
            onPointerDown={(event) => {
                backdropPressRef.current = event.target === event.currentTarget;
            }}
            onPointerCancel={() => { backdropPressRef.current = false; }}
            onClick={(event) => {
                if (!transitionActiveRef.current && backdropPressRef.current
                    && event.target === event.currentTarget) onClose();
                backdropPressRef.current = false;
            }}
            onContextMenu={(event) => event.preventDefault()}
            onDragStart={(event) => event.preventDefault()}
            style={{
                position: "fixed",
                inset: 0,
                zIndex: 1000,
                display: "grid",
                placeItems: "center",
                padding: "20px",
                boxSizing: "border-box",
                userSelect: "none",
                WebkitUserSelect: "none",
                WebkitTouchCallout: "none",
            }}
        >
            <div
                ref={backdropRef}
                aria-hidden="true"
                style={{
                    position: "absolute",
                    inset: 0,
                    background: "rgba(0,0,0,0.48)",
                    opacity: 1,
                    pointerEvents: "none",
                }}
            />
            <div
                ref={panelRef}
                role="dialog"
                aria-label={label}
                onPointerDownCapture={(event) => {
                    if (event.pointerType === "mouse") suppressClickRef.current = false;
                }}
                onClickCapture={(event) => {
                    if (!suppressClickRef.current && !transitionActiveRef.current) return;
                    event.preventDefault();
                    event.stopPropagation();
                }}
                style={{
                    position: "relative",
                    transform: "translate3d(0, 0, 0) scale(0.95)",
                    willChange: "transform",
                    transformOrigin: "center",
                    ...panelStyle,
                }}
            >
                {children}
            </div>
        </div>,
        document.body
    );
}
