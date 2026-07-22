export function measureStageWidth(stage) {
    return stage?.offsetWidth ?? 0;
}

export function readViewportDimensions() {
    return {
        width: window.innerWidth,
        height: window.innerHeight,
    };
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
export function scrollStageTo(stage, left) {
    stage.scrollTo({
        left,
        behavior: "smooth",
    });
}