import { useEffect, useRef } from "react";

const DRAG_SLOP = 10;
const VERTICAL_INTENT_RATIO = 1.15;
const MIN_DISMISS_DISTANCE = 75;
const MAX_DISMISS_DISTANCE = 150;
const DISMISS_VIEWPORT_RATIO = 0.17;
const MIN_SCALE = 0.9;
const SCALE_DISTANCE_MULTIPLIER = 1.35;
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
    const suppressClickTimerRef = useRef(null);
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

    const expireClickSuppression = () => {
        if (suppressClickTimerRef.current !== null) {
            clearTimeout(suppressClickTimerRef.current);
        }
        suppressClickTimerRef.current = setTimeout(() => {
            suppressNextClickRef.current = false;
            suppressClickTimerRef.current = null;
        }, 0);
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

        transitionEndRef.current = finish;
        visualRef.current?.addEventListener("transitionend", finish, {
            once: true,
        });
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
        const viewportHeight = window.visualViewport?.height || window.innerHeight;
        const direction = gesture.dy < 0 ? -1 : 1;
        const targetY = direction * Math.max(
            Math.abs(gesture.dy) + 120,
            viewportHeight * 0.55
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
            x: gesture.dx,
            y: targetY,
            scale: MIN_SCALE,
            backdropAlpha: 0,
        });
        waitForTransition(DISMISS_DURATION_MS, onDismiss);
    };

    const handlePointerDown = event => {
        if (!event.isPrimary || gestureRef.current.phase !== "idle") return;

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

            if (Math.abs(dy) < VERTICAL_INTENT_RATIO * Math.abs(dx)) {
                gesture.phase = "cancelled";
                suppressNextClickRef.current = true;
                return;
            }

            gesture.phase = "dragging";
            suppressNextClickRef.current = true;
            event.currentTarget.setPointerCapture?.(event.pointerId);
        }

        const viewportHeight = window.visualViewport?.height || window.innerHeight;
        const dismissDistance = Math.min(
            MAX_DISMISS_DISTANCE,
            Math.max(MIN_DISMISS_DISTANCE, viewportHeight * DISMISS_VIEWPORT_RATIO)
        );
        const progress = Math.min(1, Math.abs(dy) / dismissDistance);
        const scaleProgress = Math.min(
            1,
            Math.abs(dy) / (dismissDistance * SCALE_DISTANCE_MULTIPLIER)
        );

        setVisual({
            x: dx,
            y: dy,
            scale: 1 - (1 - MIN_SCALE) * scaleProgress,
            backdropAlpha: 0.97 - 0.4 * progress,
        });
    };

    const handlePointerUp = event => {
        const gesture = gestureRef.current;
        const pointerUpDx = event.clientX - gesture.startX;
        const pointerUpDy = event.clientY - gesture.startY;
        if (!event.isPrimary || event.pointerId !== gesture.pointerId) return;

        if (gesture.phase === "dragging") {
            expireClickSuppression();
            gesture.dx = pointerUpDx;
            gesture.dy = pointerUpDy;
            const viewportHeight = window.visualViewport?.height || window.innerHeight;
            const dismissDistance = Math.min(
                MAX_DISMISS_DISTANCE,
                Math.max(MIN_DISMISS_DISTANCE, viewportHeight * DISMISS_VIEWPORT_RATIO)
            );
            if (Math.abs(pointerUpDy) >= dismissDistance) dismiss();
            else restore();
            return;
        }

        if (gesture.phase === "cancelled") {
            expireClickSuppression();
            gestureRef.current = initialGesture();
            return;
        }

        gestureRef.current = initialGesture();
    };

    const handlePointerCancel = event => {
        const gesture = gestureRef.current;
        if (event.pointerId !== gesture.pointerId) return;

        suppressNextClickRef.current = false;
        if (gesture.phase === "dragging") restore();
        else gestureRef.current = initialGesture();
    };

    const handleLostPointerCapture = () => {};

    const handleClick = () => {
        if (suppressNextClickRef.current) {
            suppressNextClickRef.current = false;
            return;
        }
        onDismiss();
    };

    useEffect(() => () => {
        clearTransitionWait();
        if (suppressClickTimerRef.current !== null) {
            clearTimeout(suppressClickTimerRef.current);
        }
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
