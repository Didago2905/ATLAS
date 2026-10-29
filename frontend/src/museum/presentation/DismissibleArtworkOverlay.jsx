import { useEffect, useRef } from "react";

const DRAG_SLOP = 10;
const MIN_DISMISS_DISTANCE = 75;
const MAX_DISMISS_DISTANCE = 150;
const DISMISS_VIEWPORT_RATIO = 0.17;
const MIN_SCALE = 0.85;
const RESTORE_DURATION_MS = 250;
const DISMISS_DURATION_MS = 220;
const TRANSITION_EASING = "cubic-bezier(0.22, 1, 0.36, 1)";

const initialGesture = () => ({
    phase: "idle",
    pointerId: null,
    startX: 0,
    startY: 0,
    dx: 0,
    dy: 0,
});

export default function DismissibleArtworkOverlay({ artwork, background, onDismiss }) {
    const surfaceRef = useRef(null);
    const backdropRef = useRef(null);
    const visualRef = useRef(null);
    const gestureRef = useRef(initialGesture());
    const suppressNextClickRef = useRef(false);
    const touchPointersRef = useRef(new Set());
    const multitouchRef = useRef(false);
    const dismissedRef = useRef(false);
    const transitionTimerRef = useRef(null);
    const transitionEndRef = useRef(null);
    const clearTransitionWait = () => {
        if (transitionTimerRef.current !== null) {
            clearTimeout(transitionTimerRef.current);
            transitionTimerRef.current = null;
        }

        if (transitionEndRef.current && visualRef.current) {
            visualRef.current.removeEventListener(
                "transitionend",
                transitionEndRef.current
            );
            transitionEndRef.current = null;
        }
    };

    const completeDismiss = () => {
        if (dismissedRef.current) return;
        dismissedRef.current = true;
        onDismiss();
    };

    const dragGeometry = (dx, dy) => {
        const width = window.visualViewport?.width || window.innerWidth;
        const height = window.visualViewport?.height || window.innerHeight;
        const threshold = size => Math.min(MAX_DISMISS_DISTANCE,
            Math.max(MIN_DISMISS_DISTANCE, size * DISMISS_VIEWPORT_RATIO));
        const horizontal = Math.abs(dx) > Math.abs(dy);
        const thresholdX = threshold(width);
        const thresholdY = threshold(height);
        // Normalize both axes continuously so changing the dominant axis cannot
        // jump the scale. The slop starts at scale 1; either threshold reaches .90.
        const scaleProgress = Math.max(0,
            (Math.abs(dx) - DRAG_SLOP) / (thresholdX - DRAG_SLOP),
            (Math.abs(dy) - DRAG_SLOP) / (thresholdY - DRAG_SLOP));
        return {
            horizontal,
            displacement: horizontal ? dx : dy,
            viewportSize: horizontal ? width : height,
            threshold: horizontal ? thresholdX : thresholdY,
            scale: Math.max(MIN_SCALE, 1 - 0.10 * scaleProgress),
            fadeProgress: Math.min(1, Math.max(Math.abs(dx) / thresholdX, Math.abs(dy) / thresholdY)),
        };
    };

    const setVisual = ({ x, y, scale, backdropAlpha }) => {
        if (visualRef.current) {
            visualRef.current.style.transform =
                `translate3d(${x}px, ${y}px, 0) scale(${scale})`;
        }
        if (backdropRef.current) {
            backdropRef.current.style.opacity = String(backdropAlpha / 0.97);
        }
    };

    const waitForTransition = (duration, complete) => {
        clearTransitionWait();

        let completed = false;
        const finish = () => {
            if (completed) return;
            completed = true;
            clearTransitionWait();
            complete();
        };

        transitionEndRef.current = event => {
            if (event.target === visualRef.current && event.propertyName === "transform") finish();
        };
        visualRef.current?.addEventListener("transitionend", transitionEndRef.current);
        transitionTimerRef.current = setTimeout(finish, duration + 80);
    };

    const restore = () => {
        const gesture = gestureRef.current;
        gesture.phase = "restoring";

        if (visualRef.current) {
            visualRef.current.style.transition =
                `transform ${RESTORE_DURATION_MS}ms ${TRANSITION_EASING}`;
        }
        if (backdropRef.current) {
            backdropRef.current.style.transition =
                `opacity ${RESTORE_DURATION_MS}ms ${TRANSITION_EASING}`;
        }

        setVisual({ x: 0, y: 0, scale: 1, backdropAlpha: 0.97 });
        waitForTransition(RESTORE_DURATION_MS, () => {
            if (visualRef.current) visualRef.current.style.transition = "";
            if (backdropRef.current) backdropRef.current.style.transition = "";
            gestureRef.current = initialGesture();
        });
    };

    const dismiss = () => {
        const gesture = gestureRef.current;
        gesture.phase = "dismissing";
        const { horizontal, displacement, viewportSize } = dragGeometry(gesture.dx, gesture.dy);
        const visualSize = horizontal ? visualRef.current?.offsetWidth : visualRef.current?.offsetHeight;
        const target = Math.sign(displacement) * Math.max(
            Math.abs(displacement) + 120,
            viewportSize * 0.55,
            viewportSize / 2 + (visualSize || 0) * MIN_SCALE / 2 + 24
        );

        if (visualRef.current) {
            visualRef.current.style.transition =
                `transform ${DISMISS_DURATION_MS}ms ${TRANSITION_EASING}`;
        }
        if (backdropRef.current) {
            backdropRef.current.style.transition =
                `opacity ${DISMISS_DURATION_MS}ms ${TRANSITION_EASING}`;
        }

        setVisual({
            x: horizontal ? target : gesture.dx,
            y: horizontal ? gesture.dy : target,
            scale: MIN_SCALE,
            backdropAlpha: 0,
        });
        waitForTransition(DISMISS_DURATION_MS, completeDismiss);
    };

    const cancelGesture = () => {
        const gesture = gestureRef.current;
        if (gesture.phase !== "pending" && gesture.phase !== "dragging") return;
        suppressNextClickRef.current = true;
        if (gesture.phase === "dragging") restore();
        else gestureRef.current = initialGesture();
        if (surfaceRef.current?.hasPointerCapture?.(gesture.pointerId)) {
            surfaceRef.current.releasePointerCapture(gesture.pointerId);
        }
    };

    const handlePointerDown = event => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        if (!event.isPrimary || multitouchRef.current || gestureRef.current.phase !== "idle"
            || dismissedRef.current) return;
        suppressNextClickRef.current = false;

        gestureRef.current = {
            phase: "pending",
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            dx: 0,
            dy: 0,
        };
    };

    const handlePointerMove = event => {
        const gesture = gestureRef.current;
        if (!event.isPrimary || event.pointerId !== gesture.pointerId) return;
        if (gesture.phase !== "pending" && gesture.phase !== "dragging") return;

        const dx = event.clientX - gesture.startX;
        const dy = event.clientY - gesture.startY;
        gesture.dx = dx;
        gesture.dy = dy;

        if (gesture.phase === "pending") {
            if (Math.hypot(dx, dy) < DRAG_SLOP) return;

            gesture.phase = "dragging";
            suppressNextClickRef.current = true;
            try {
                event.currentTarget.setPointerCapture?.(event.pointerId);
            } catch {
                cancelGesture();
                return;
            }
        }

        const { scale, fadeProgress } = dragGeometry(dx, dy);

        setVisual({
            x: dx,
            y: dy,
            scale,
            backdropAlpha: 0.97 - 0.4 * fadeProgress,
        });
    };

    const handlePointerUp = event => {
        const gesture = gestureRef.current;
        const pointerUpDx = event.clientX - gesture.startX;
        const pointerUpDy = event.clientY - gesture.startY;
        if (!event.isPrimary || event.pointerId !== gesture.pointerId) return;

        if (gesture.phase === "dragging") {
            gesture.dx = pointerUpDx;
            gesture.dy = pointerUpDy;
            const { displacement, threshold } = dragGeometry(pointerUpDx, pointerUpDy);
            if (Math.abs(displacement) >= threshold) dismiss();
            else restore();
            return;
        }

        if (gesture.phase === "pending") gestureRef.current = initialGesture();
    };

    const handlePointerCancel = event => {
        const gesture = gestureRef.current;
        if (event.pointerId !== gesture.pointerId) return;

        cancelGesture();
    };

    const handleLostPointerCapture = event => {
        // Touch starts with implicit capture on the hit child. Moving capture to
        // the surface emits a bubbled loss from that child, not an interruption.
        if (event.target === surfaceRef.current) handlePointerCancel(event);
    };

    const handleClick = () => {
        if (suppressNextClickRef.current || multitouchRef.current
            || gestureRef.current.phase !== "idle") return;
        completeDismiss();
    };

    useEffect(() => {
        // Observe all contacts, including a second finger outside the surface.
        const down = event => {
            if (event.pointerType !== "touch") return;
            touchPointersRef.current.add(event.pointerId);
            if (touchPointersRef.current.size > 1 || !event.isPrimary) {
                multitouchRef.current = true;
                suppressNextClickRef.current = true;
                cancelGesture();
            }
        };
        const end = event => {
            touchPointersRef.current.delete(event.pointerId);
            if (!touchPointersRef.current.size) multitouchRef.current = false;
        };
        const interrupt = () => {
            touchPointersRef.current.clear();
            multitouchRef.current = false;
            cancelGesture();
        };
        const visibility = () => { if (document.hidden) interrupt(); };
        window.addEventListener("pointerdown", down, true);
        window.addEventListener("pointerup", end, true);
        window.addEventListener("pointercancel", end, true);
        window.addEventListener("blur", interrupt);
        document.addEventListener("visibilitychange", visibility);
        return () => {
            clearTransitionWait();
            window.removeEventListener("pointerdown", down, true);
            window.removeEventListener("pointerup", end, true);
            window.removeEventListener("pointercancel", end, true);
            window.removeEventListener("blur", interrupt);
            document.removeEventListener("visibilitychange", visibility);
            touchPointersRef.current.clear();
        };
    }, []);

    return (
        <div
            ref={surfaceRef}
            data-atlas-museum-artwork-overlay
            onClick={handleClick}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onLostPointerCapture={handleLostPointerCapture}
            style={{
                position: "fixed",
                inset: 0,
                width: "100vw",
                height: "100vh",
                background: "transparent",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 9999,
                cursor: "pointer",
                WebkitTapHighlightColor: "transparent",
                touchAction: "none",
                WebkitUserSelect: "none",
                userSelect: "none",
                WebkitTouchCallout: "none",
            }}
        >
            <div
                ref={backdropRef}
                data-atlas-museum-artwork-background
                aria-hidden="true"
                style={{
                    position: "absolute",
                    inset: 0,
                    background,
                    opacity: 1,
                    pointerEvents: "none",
                }}
            />
            <div
                ref={visualRef}
                data-atlas-museum-artwork-visual
                style={{
                    display: "flex",
                    position: "relative",
                    zIndex: 1,
                    alignItems: "center",
                    justifyContent: "center",
                    maxWidth: "95%",
                    maxHeight: "95%",
                    willChange: "transform",
                    transform: "translate3d(0, 0, 0) scale(1)",
                    WebkitUserSelect: "none",
                    userSelect: "none",
                    WebkitTouchCallout: "none",
                }}
            >
                <img
                    src={artwork.image_url}
                    alt={artwork.name || ""}
                    draggable={false}
                    style={{
                        display: "block",
                        maxWidth: "100%",
                        maxHeight: "95vh",
                        objectFit: "contain",
                        pointerEvents: "none",
                        WebkitUserSelect: "none",
                        userSelect: "none",
                        WebkitTouchCallout: "none",
                    }}
                />
            </div>
        </div>
    );
}
