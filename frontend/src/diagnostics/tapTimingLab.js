const roundMs = (value) => Math.round(value * 1000) / 1000;

export function createTapTimingLab() {
    let startedAt = performance.now();
    let startedDateNow = Date.now();
    let trace = [];
    let attempts = [];
    let currentAttempt = null;
    let nextAttemptNumber = 1;
    let nextRawSequence = 1;
    const subscribers = new Set();

    const relativeNow = () => roundMs(performance.now() - startedAt);
    const notify = () => subscribers.forEach(callback => callback());
    const snapshotAttempt = attempt => attempt ? { ...attempt } : null;
    const snapshotTouch = touch => ({
        identifier: touch.identifier,
        clientX: touch.clientX,
        clientY: touch.clientY,
        pageX: touch.pageX,
        pageY: touch.pageY,
        screenX: touch.screenX,
        screenY: touch.screenY,
    });

    const rawEventDetails = event => ({
        raw: true,
        sequence: nextRawSequence++,
        eventType: event.type,
        eventTimeStamp: event.timeStamp,
        dateNowRelativeMs: Date.now() - startedDateNow,
        touchesLength: event.touches.length,
        changedTouchesLength: event.changedTouches.length,
        touches: Array.from(event.touches, snapshotTouch),
        changedTouches: Array.from(event.changedTouches, snapshotTouch),
    });

    const addTrace = (type, details = {}, at = relativeNow()) => {
        trace.push({ type, at, ...details });
        notify();
        return at;
    };

    const beginAttempt = (at) => {
        currentAttempt = {
            attempt: nextAttemptNumber++,
            firstChordAt: at,
            releaseAt: null,
            secondChordAt: null,
            chordToChordMs: null,
            releaseToSecondChordMs: null,
            firstChordToReleaseMs: null,
            toggleRecognized: false,
        };
        attempts.push(currentAttempt);
    };

    const api = {
        reset() {
            startedAt = performance.now();
            startedDateNow = Date.now();
            trace = [];
            attempts = [];
            currentAttempt = null;
            nextAttemptNumber = 1;
            nextRawSequence = 1;
            notify();
        },
        getTrace() {
            return trace.map(entry => ({ ...entry }));
        },
        getSummary() {
            const snapshots = attempts.map(snapshotAttempt);
            return {
                attempts: snapshots,
                lastAttempt: snapshots.at(-1) || null,
            };
        },
        exportSession() {
            return {
                meta: {
                    lab: "ATLAS_TAP_TIMING_LAB",
                    version: 1,
                    exportedAt: new Date().toISOString(),
                    location: window.location.href,
                    userAgent: navigator.userAgent,
                    thresholdMs: 350,
                },
                summary: api.getSummary(),
                trace: api.getTrace(),
            };
        },
        exportTrace() {
            return JSON.stringify(api.exportSession(), null, 2);
        },
        subscribe(callback) {
            subscribers.add(callback);
            return () => subscribers.delete(callback);
        },
        recordTouchStart(event) {
            const rawEvent = rawEventDetails(event);
            const at = addTrace("TOUCHSTART", rawEvent);

            if (event.touches.length < 2) return rawEvent.sequence;

            if (!currentAttempt || currentAttempt.secondChordAt !== null) {
                beginAttempt(at);
            } else {
                currentAttempt.secondChordAt = at;
                currentAttempt.chordToChordMs = roundMs(at - currentAttempt.firstChordAt);
                if (currentAttempt.releaseAt !== null) {
                    currentAttempt.releaseToSecondChordMs = roundMs(at - currentAttempt.releaseAt);
                }
            }

            addTrace("TWO_FINGER_CHORD", {
                attempt: currentAttempt.attempt,
                chord: currentAttempt.secondChordAt === null ? 1 : 2,
                rawEventSequence: rawEvent.sequence,
            }, at);
            return rawEvent.sequence;
        },
        recordTouchEnd(event) {
            const rawEvent = rawEventDetails(event);
            const at = addTrace("TOUCHEND", rawEvent);
            if (event.touches.length !== 0) return;

            addTrace("FULL_RELEASE", {}, at);
            if (currentAttempt && currentAttempt.secondChordAt === null) {
                currentAttempt.releaseAt = at;
                currentAttempt.firstChordToReleaseMs = roundMs(at - currentAttempt.firstChordAt);
                notify();
            }
        },
        recordCancel(event) {
            addTrace("CANCEL", rawEventDetails(event));
            if (currentAttempt && currentAttempt.secondChordAt === null) {
                attempts = attempts.filter(attempt => attempt !== currentAttempt);
            }
            currentAttempt = null;
            notify();
        },
        recordPhysicalChord({ classification, identifiers, rawEventSequence }) {
            addTrace(classification, {
                identifiers: [...identifiers],
                rawEventSequence,
            });
        },
        recordProductiveDecision(decision) {
            addTrace("PRODUCTIVE_DECISION", decision);
            if (currentAttempt) {
                currentAttempt.toggleRecognized = decision.recognized;
                notify();
            }
        },
    };

    return api;
}
