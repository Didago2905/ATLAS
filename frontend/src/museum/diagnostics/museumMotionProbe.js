const GLOBAL_NAME = "__ATLAS_MUSEUM_MOTION_PROBE__";
const MAX_EVENTS = 4000;
const MAX_SAMPLES = 6000;
const SETTLE_QUIET_MS = 200;
const SETTLE_VELOCITY_PX_PER_MS = 0.02;
const SETTLE_STABLE_FRAMES = 6;

const now = () => performance.now();

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function percentile(values, ratio) {
    if (!values.length) return null;

    const sorted = [...values].sort((a, b) => a - b);
    const index = Math.min(
        sorted.length - 1,
        Math.floor(sorted.length * ratio)
    );

    return sorted[index];
}

export function installMuseumMotionProbe(stage) {
    if (!stage || window[GLOBAL_NAME]) {
        return () => { };
    }

    const track = stage.querySelector("[data-atlas-museum-track]");
    const events = [];
    const samples = [];
    const startedAt = now();

    let droppedEvents = 0;
    let droppedSamples = 0;
    let frame = null;
    let lastFrameAt = null;
    let lastSampleLeft = stage.scrollLeft;
    let lastVelocity = 0;
    let lastScrollAt = null;
    let lastTouchEndAt = null;
    let touching = false;
    let stableFrames = 0;
    let settledAt = null;
    let selectedArtworkId = null;
    let geometryDirty = true;
    let geometry = [];
    let stageWidth = stage.clientWidth;
    let stageViewportCenterX = null;
    let centerRequestSequence = 0;
    let pendingCenterRequest = null;

    const pushBounded = (buffer, value, limit, onDrop) => {
        if (buffer.length >= limit) {
            buffer.shift();
            onDrop();
        }

        buffer.push(value);
    };

    const pushEvent = (type, details = {}, timestamp = now()) => {
        pushBounded(
            events,
            { type, t: timestamp, ...details },
            MAX_EVENTS,
            () => { droppedEvents += 1; }
        );
    };

    const refreshGeometry = (reason) => {
        if (!track) return;

        stageWidth = stage.clientWidth;
        const stageRect = stage.getBoundingClientRect();
        stageViewportCenterX = stageRect.left + stageWidth / 2;

        geometry = Array.from(track.children)
            .filter(node => node.matches("[data-atlas-museum-card]"))
            .map((slot, index) => ({
                id: slot.dataset.atlasMuseumCardId || String(index),
                index,
                layoutCenter: slot.offsetLeft + slot.offsetWidth / 2,
                visual: slot.querySelector("[data-atlas-museum-visual]"),
            }));

        geometryDirty = false;
        pushEvent("geometry:refresh", {
            reason,
            cardCount: geometry.length,
            stageWidth,
        });
    };

    const findNearest = (center) => geometry.reduce((nearest, card) => {
        const distance = Math.abs(card.layoutCenter - center);

        return !nearest || distance < nearest.distance
            ? { ...card, distance }
            : nearest;
    }, null);

    const getSummary = () => {
        const finalSample = samples[samples.length - 1] || null;
        const frameDeltas = samples
            .map(sample => sample.frameDelta)
            .filter(value => Number.isFinite(value));
        const touchEnds = events.filter(event => event.type === "touch:end");
        const clicks = events.filter(event => event.type === "click");
        const centerRequests = events.filter(
            event => event.type === "navigation:center-request"
        );

        return {
            enabled: true,
            eventCount: events.length,
            sampleCount: samples.length,
            droppedEvents,
            droppedSamples,
            touching,
            sampling: frame !== null,
            selectedArtworkId,
            touchEndCount: touchEnds.length,
            clickCount: clicks.length,
            clicksAfterTouchEnd: clicks.filter(
                event => Number.isFinite(event.msSinceTouchEnd)
            ).length,
            centerRequestCount: centerRequests.length,
            pendingCenterRequest,
            settledAt,
            settlementDurationFromLastTouchEnd:
                settledAt !== null && lastTouchEndAt !== null
                    ? settledAt - lastTouchEndAt
                    : null,
            raf: {
                maxDelta: frameDeltas.length ? Math.max(...frameDeltas) : null,
                p95Delta: percentile(frameDeltas, 0.95),
            },
            final: finalSample
                ? {
                    t: finalSample.t,
                    scrollLeft: finalSample.scrollLeft,
                    velocity: finalSample.velocity,
                    nearestCardId: finalSample.nearestCardId,
                    layoutCenterDelta: finalSample.layoutCenterDelta,
                    visualCenterDelta: finalSample.visualCenterDelta,
                }
                : null,
        };
    };

    const sample = (timestamp) => {
        frame = null;

        if (geometryDirty) {
            refreshGeometry("sampler");
        }

        const scrollLeft = stage.scrollLeft;
        const frameDelta = lastFrameAt === null ? null : timestamp - lastFrameAt;
        const velocity = frameDelta && frameDelta > 0
            ? (scrollLeft - lastSampleLeft) / frameDelta
            : 0;
        const layoutStageCenter = scrollLeft + stageWidth / 2;
        const nearest = findNearest(layoutStageCenter);
        const visualRect = nearest?.visual?.getBoundingClientRect() || null;
        const visualCenter = visualRect
            ? visualRect.left + visualRect.width / 2
            : null;

        lastFrameAt = timestamp;
        lastSampleLeft = scrollLeft;
        lastVelocity = velocity;

        pushBounded(
            samples,
            {
                t: timestamp,
                frameDelta,
                scrollLeft,
                velocity,
                stageCenter: layoutStageCenter,
                viewportCenter: stageViewportCenterX,
                nearestCardId: nearest?.id ?? null,
                nearestCardIndex: nearest?.index ?? null,
                nearestLayoutCenter: nearest?.layoutCenter ?? null,
                nearestVisualCenter: visualCenter,
                layoutCenterDelta: nearest
                    ? nearest.layoutCenter - layoutStageCenter
                    : null,
                visualCenterDelta:
                    visualCenter !== null && stageViewportCenterX !== null
                        ? visualCenter - stageViewportCenterX
                        : null,
                selectedArtworkId,
                touching,
                pendingCenterRequestId: pendingCenterRequest?.id ?? null,
            },
            MAX_SAMPLES,
            () => { droppedSamples += 1; }
        );

        const quietSince = Math.max(
            lastScrollAt ?? 0,
            lastTouchEndAt ?? 0,
            pendingCenterRequest?.requestedAt ?? 0,
            startedAt
        );
        const quietFor = timestamp - quietSince;
        const slowEnough = Math.abs(velocity) <= SETTLE_VELOCITY_PX_PER_MS;

        stableFrames = !touching && slowEnough ? stableFrames + 1 : 0;

        if (
            !touching &&
            quietFor >= SETTLE_QUIET_MS &&
            stableFrames >= SETTLE_STABLE_FRAMES
        ) {
            settledAt = timestamp;
            pushEvent("settled", {
                scrollLeft,
                velocity,
                nearestCardId: nearest?.id ?? null,
                layoutCenterDelta: nearest
                    ? nearest.layoutCenter - layoutStageCenter
                    : null,
                visualCenterDelta:
                    visualCenter !== null && stageViewportCenterX !== null
                        ? visualCenter - stageViewportCenterX
                        : null,
                pendingCenterRequestId: pendingCenterRequest?.id ?? null,
                derived: true,
            }, timestamp);
            pendingCenterRequest = null;
            return;
        }

        frame = requestAnimationFrame(sample);
    };

    const ensureSampler = () => {
        if (frame !== null) return;

        settledAt = null;
        stableFrames = 0;
        lastFrameAt = null;
        lastSampleLeft = stage.scrollLeft;
        frame = requestAnimationFrame(sample);
    };

    const touchDetails = (event) => {
        const touch = event.touches[0] || event.changedTouches[0];

        return {
            x: touch?.clientX ?? null,
            y: touch?.clientY ?? null,
            touchCount: event.touches.length,
        };
    };

    const handleTouchStart = (event) => {
        const timestamp = now();
        touching = true;
        geometryDirty = true;
        pushEvent("touch:start", {
            ...touchDetails(event),
            eventTimeStamp: event.timeStamp,
        }, timestamp);
        ensureSampler();
    };

    const handleTouchMove = (event) => {
        pushEvent("touch:move", {
            ...touchDetails(event),
            eventTimeStamp: event.timeStamp,
        });
    };

    const handleTouchEnd = (event) => {
        const timestamp = now();
        touching = event.touches.length > 0;
        lastTouchEndAt = timestamp;
        pushEvent("touch:end", {
            ...touchDetails(event),
            eventTimeStamp: event.timeStamp,
        }, timestamp);
        ensureSampler();
    };

    const handleTouchCancel = (event) => {
        const timestamp = now();
        touching = event.touches.length > 0;
        lastTouchEndAt = timestamp;
        pushEvent("touch:cancel", {
            ...touchDetails(event),
            eventTimeStamp: event.timeStamp,
        }, timestamp);
        ensureSampler();
    };

    const handleClick = (event) => {
        const timestamp = now();
        const slot = event.target.closest?.("[data-atlas-museum-card]");

        pushEvent("click", {
            cardId: slot?.dataset.atlasMuseumCardId ?? null,
            scrollLeft: stage.scrollLeft,
            velocity: lastVelocity,
            msSinceTouchEnd: lastTouchEndAt === null
                ? null
                : timestamp - lastTouchEndAt,
            eventTimeStamp: event.timeStamp,
        }, timestamp);
        ensureSampler();
    };

    const handleScroll = (event) => {
        const timestamp = now();
        lastScrollAt = timestamp;
        pushEvent("scroll", {
            scrollLeft: stage.scrollLeft,
            eventTimeStamp: event.timeStamp,
        }, timestamp);
        ensureSampler();
    };

    const handleScrollEnd = (event) => {
        pushEvent("scrollend", {
            scrollLeft: stage.scrollLeft,
            browserEvent: true,
            eventTimeStamp: event.timeStamp,
        });
    };

    const invalidateGeometry = () => {
        geometryDirty = true;
    };

    const mutationObserver = new MutationObserver(invalidateGeometry);
    mutationObserver.observe(track || stage, {
        childList: true,
        subtree: true,
    });

    stage.addEventListener("touchstart", handleTouchStart, { passive: true });
    stage.addEventListener("touchmove", handleTouchMove, { passive: true });
    stage.addEventListener("touchend", handleTouchEnd, { passive: true });
    stage.addEventListener("touchcancel", handleTouchCancel, { passive: true });
    stage.addEventListener("click", handleClick, { passive: true, capture: true });
    stage.addEventListener("scroll", handleScroll, { passive: true });
    stage.addEventListener("scrollend", handleScrollEnd, { passive: true });
    window.addEventListener("resize", invalidateGeometry, { passive: true });
    window.visualViewport?.addEventListener("resize", invalidateGeometry, {
        passive: true,
    });

    refreshGeometry("install");

    const api = {
        status() {
            return {
                enabled: true,
                installedAt: startedAt,
                cardCount: geometry.length,
                eventCount: events.length,
                sampleCount: samples.length,
                touching,
                sampling: frame !== null,
                geometryDirty,
                selectedArtworkId,
                lastVelocity,
                lastTouchEndAt,
                lastScrollAt,
                settledAt,
                pendingCenterRequest: clone(pendingCenterRequest),
                limits: {
                    events: MAX_EVENTS,
                    samples: MAX_SAMPLES,
                },
            };
        },

        reset() {
            if (frame !== null) {
                cancelAnimationFrame(frame);
                frame = null;
            }

            events.length = 0;
            samples.length = 0;
            droppedEvents = 0;
            droppedSamples = 0;
            lastFrameAt = null;
            lastSampleLeft = stage.scrollLeft;
            lastVelocity = 0;
            lastScrollAt = null;
            lastTouchEndAt = null;
            touching = false;
            stableFrames = 0;
            settledAt = null;
            pendingCenterRequest = null;
            geometryDirty = true;

            pushEvent("capture:reset", { scrollLeft: stage.scrollLeft });
            return this.status();
        },

        getTrace() {
            return clone({
                metadata: {
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    devicePixelRatio: window.devicePixelRatio,
                    visualViewport: window.visualViewport
                        ? {
                            width: window.visualViewport.width,
                            height: window.visualViewport.height,
                            scale: window.visualViewport.scale,
                        }
                        : null,
                    limits: {
                        events: MAX_EVENTS,
                        samples: MAX_SAMPLES,
                    },
                    droppedEvents,
                    droppedSamples,
                },
                events,
                samples,
                summary: getSummary(),
            });
        },

        exportTrace() {
            return JSON.stringify(this.getTrace(), null, 2);
        },

        getSummary() {
            return clone(getSummary());
        },

        markNavigationCenterRequest(details) {
            const timestamp = now();
            centerRequestSequence += 1;
            pendingCenterRequest = {
                id: centerRequestSequence,
                requestedAt: timestamp,
                cardId: details.cardId ?? null,
                targetLeft: details.targetLeft,
            };
            pushEvent("navigation:center-request", {
                ...pendingCenterRequest,
                scrollLeft: stage.scrollLeft,
                velocity: lastVelocity,
                layoutCenterDelta: details.layoutCenterDelta,
                msSinceTouchEnd: lastTouchEndAt === null
                    ? null
                    : timestamp - lastTouchEndAt,
            }, timestamp);
            ensureSampler();
            return pendingCenterRequest.id;
        },

        markNavigationCenterStart(details) {
            const timestamp = now();
            pushEvent("navigation:center-start", {
                requestId: pendingCenterRequest?.id ?? null,
                targetLeft: details.targetLeft,
                behavior: details.behavior,
                scrollLeft: stage.scrollLeft,
                velocity: lastVelocity,
            }, timestamp);
            ensureSampler();
        },

        markSelectionChange(details) {
            selectedArtworkId = details.artworkId ?? null;
            pushEvent("selection:change", {
                artworkId: selectedArtworkId,
            });
        },
    };

    window[GLOBAL_NAME] = api;

    return () => {
        if (frame !== null) cancelAnimationFrame(frame);
        mutationObserver.disconnect();
        stage.removeEventListener("touchstart", handleTouchStart);
        stage.removeEventListener("touchmove", handleTouchMove);
        stage.removeEventListener("touchend", handleTouchEnd);
        stage.removeEventListener("touchcancel", handleTouchCancel);
        stage.removeEventListener("click", handleClick, true);
        stage.removeEventListener("scroll", handleScroll);
        stage.removeEventListener("scrollend", handleScrollEnd);
        window.removeEventListener("resize", invalidateGeometry);
        window.visualViewport?.removeEventListener("resize", invalidateGeometry);

        if (window[GLOBAL_NAME] === api) {
            delete window[GLOBAL_NAME];
        }
    };
}
