export const tutorialOutcomeKey = "atlas_tutorial_outcome_v1";
export const tutorialProgressKey = "atlas_tutorial_progress_v1";

let outcomeFallback = null;
let outcomeOverride = false;
let active = false;
const interruptedDocument = ["reload", "back_forward"].includes(performance.getEntriesByType("navigation")[0]?.type);
const interruptedEntryKey = interruptedDocument ? window.history.state?.key || "default" : null;

export function readTutorialOutcome() {
    if (outcomeOverride) return outcomeFallback;
    try {
        const value = localStorage.getItem(tutorialOutcomeKey);
        if (value === "omitted" || value === "completed") return value;
    } catch { /* Keep the current tab usable when storage is blocked. */ }
    return outcomeFallback;
}

export function clearTutorialCheckpoint() {
    try { sessionStorage.removeItem(tutorialProgressKey); } catch { /* Optional storage. */ }
}

export function finishTutorial(outcome) {
    outcomeFallback = outcome;
    outcomeOverride = true;
    active = false;
    try { localStorage.setItem(tutorialOutcomeKey, outcome); } catch { /* In-memory fallback. */ }
    clearTutorialCheckpoint();
}

export function hasActiveTutorial() {
    return active && !readTutorialOutcome();
}

export function isExplicitTutorialStart(location) {
    const query = new URLSearchParams(location.search);
    return query.get("tutorial") === "1" && query.get("restart") === "1";
}

export function beginTutorial() {
    outcomeFallback = null;
    outcomeOverride = true;
    try { localStorage.removeItem(tutorialOutcomeKey); } catch { /* Optional storage. */ }
    clearTutorialCheckpoint();
    active = true;
}

export function resolveHomeTutorial(location) {
    const reloading = interruptedEntryKey !== null && location.key === interruptedEntryKey;
    // A reload of an old launch URL is an interruption, not a new request.
    if (isExplicitTutorialStart(location) && (!reloading || active)) {
        beginTutorial();
        return "welcome";
    }
    if (readTutorialOutcome()) {
        clearTutorialCheckpoint();
        return "normal";
    }
    let checkpoint = null;
    try { checkpoint = sessionStorage.getItem(tutorialProgressKey); } catch { /* Optional storage. */ }
    const returning = location.state?.tutorialStep === "home-after-beerdetail" || checkpoint === "home-after-beerdetail";
    const requested = new URLSearchParams(location.search).get("tutorial") === "1";
    if (!active && ((interruptedDocument && requested) || returning)) {
        finishTutorial("omitted");
        return "normal";
    }
    if (returning) return "epilogue";
    if (requested) {
        active = true;
        return "welcome";
    }
    return "normal";
}
