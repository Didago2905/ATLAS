export function measureStageWidth(stage) {
    return stage?.offsetWidth ?? 0;
}

export function readOrientation() {
    return window.innerWidth > window.innerHeight;
}

export function scheduleNextFrame(callback) {
    const frame = requestAnimationFrame(callback);

    return () => cancelAnimationFrame(frame);
}

export function observeWindowResize(callback) {
    window.addEventListener("resize", callback);

    return () => {
        window.removeEventListener("resize", callback);
    };
}

export function observeStageScroll(stage, callback) {
    if (!stage) {
        return () => { };
    }

    stage.addEventListener("scroll", callback, {
        passive: true,
    });

    return () => {
        stage.removeEventListener("scroll", callback);
    };
}