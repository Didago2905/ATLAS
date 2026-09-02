const GLOBAL_NAME = "__ATLAS_MUSEUM_MOTION_PROBE__";
const ROOT_ID = "atlas-museum-motion-probe-controls";

const formatValue = value => value == null ? "—" : String(value);
const formatNumber = value => Number.isFinite(value) ? value.toFixed(2) : "—";

function timestampForFilename() {
    return new Date().toISOString().replace(/[:.]/g, "-");
}

function cleanLabel(value) {
    return value.trim().toLowerCase()
        .replace(/[^a-z0-9_-]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 40);
}

function traceFile(label) {
    const probe = window[GLOBAL_NAME];
    const json = probe.exportTrace();
    const prefix = cleanLabel(label);
    const name = `atlas-museum-motion-${prefix ? `${prefix}-` : ""}${timestampForFilename()}.json`;
    return { json, name, blob: new Blob([json], { type: "application/json" }) };
}

function downloadTrace(file) {
    const url = URL.createObjectURL(file.blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function copyTrace(json) {
    if (!navigator.clipboard?.writeText) return false;

    try {
        await navigator.clipboard.writeText(json);
        return true;
    } catch {
        return false;
    }
}

function showTextFallback(output, json, message) {
    output.value = json;
    output.hidden = false;
    output.focus();
    output.select();
    return `${message} Trace text selected below.`;
}

function summaryText(summary) {
    const final = summary.final || {};
    return [
        `events: ${formatValue(summary.eventCount)}`,
        `samples: ${formatValue(summary.sampleCount)}`,
        `touch ends: ${formatValue(summary.touchEndCount)}`,
        `clicks: ${formatValue(summary.clickCount)}`,
        `settled: ${summary.settledAt == null ? "no" : "yes"}`,
        `settlement ms: ${formatNumber(summary.settlementDurationFromLastTouchEnd)}`,
        `final scrollLeft: ${formatNumber(final.scrollLeft)}`,
        `final nearest card: ${formatValue(final.nearestCardId)}`,
        `layout center delta: ${formatNumber(final.layoutCenterDelta)}`,
        `visual center delta: ${formatNumber(final.visualCenterDelta)}`,
        `RAF max / p95 ms: ${formatNumber(summary.raf?.maxDelta)} / ${formatNumber(summary.raf?.p95Delta)}`,
        `dropped events / samples: ${summary.droppedEvents} / ${summary.droppedSamples}`,
    ].join("\n");
}

export function installMuseumMotionProbeControls() {
    if (!window[GLOBAL_NAME] || document.getElementById(ROOT_ID)) return () => {};

    const root = document.createElement("aside");
    root.id = ROOT_ID;
    root.dataset.atlasMuseumMotionProbeControls = "";
    root.setAttribute("aria-label", "Museum motion probe controls");
    root.innerHTML = `
        <style>
            #${ROOT_ID} { position: fixed; right: max(8px, env(safe-area-inset-right)); bottom: max(8px, env(safe-area-inset-bottom)); z-index: 2147483647; width: min(268px, calc(100vw - 16px)); color: #fff; font: 12px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace; }
            #${ROOT_ID} * { box-sizing: border-box; }
            #${ROOT_ID} button, #${ROOT_ID} input { font: inherit; }
            #${ROOT_ID} .amp-pill { float: right; min-height: 38px; padding: 8px 13px; border: 1px solid #8ff; border-radius: 999px; color: #fff; background: rgba(8, 13, 18, .92); }
            #${ROOT_ID} .amp-panel { clear: both; padding: 10px; border: 1px solid #59717d; border-radius: 10px; background: rgba(8, 13, 18, .96); box-shadow: 0 3px 16px #0009; }
            #${ROOT_ID} .amp-title { margin: 0 0 8px; font-weight: 700; letter-spacing: .08em; }
            #${ROOT_ID} .amp-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
            #${ROOT_ID} .amp-actions button { min-height: 36px; padding: 6px; border: 1px solid #718791; border-radius: 6px; color: #fff; background: #17242b; }
            #${ROOT_ID} label { display: block; margin: 8px 0 4px; color: #b9c9cf; }
            #${ROOT_ID} input, #${ROOT_ID} textarea, #${ROOT_ID} pre { width: 100%; border: 1px solid #51636c; border-radius: 5px; color: #fff; background: #0d171c; }
            #${ROOT_ID} input { min-height: 34px; padding: 6px; }
            #${ROOT_ID} pre { max-height: 164px; margin: 8px 0 0; padding: 7px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
            #${ROOT_ID} textarea { height: 120px; margin-top: 8px; padding: 6px; font-size: 10px; }
            #${ROOT_ID} [hidden] { display: none !important; }
        </style>
        <button class="amp-pill" type="button" aria-expanded="false">PROBE</button>
        <section class="amp-panel" hidden>
            <p class="amp-title">MOTION PROBE</p>
            <div class="amp-actions">
                <button type="button" data-action="reset">RESET</button>
                <button type="button" data-action="status">STATUS</button>
                <button type="button" data-action="summary">SUMMARY</button>
                <button type="button" data-action="copy">COPY TRACE</button>
                <button type="button" data-action="share">SHARE / EXPORT</button>
                <button type="button" data-action="close">CLOSE</button>
            </div>
            <label>Optional experiment label</label>
            <input class="amp-label" type="text" maxlength="40" placeholder="long-swipe" autocomplete="off">
            <pre class="amp-result" aria-live="polite">Ready. Reset before each gesture.</pre>
            <textarea class="amp-fallback" readonly hidden aria-label="Selectable trace JSON"></textarea>
        </section>`;

    const pill = root.querySelector(".amp-pill");
    const panel = root.querySelector(".amp-panel");
    const result = root.querySelector(".amp-result");
    const output = root.querySelector(".amp-fallback");
    const label = root.querySelector(".amp-label");
    const setOpen = open => {
        panel.hidden = !open;
        pill.hidden = open;
        pill.setAttribute("aria-expanded", String(open));
    };

    const isolate = event => event.stopPropagation();
    ["touchstart", "touchmove", "touchend", "touchcancel", "pointerdown", "pointerup", "click"]
        .forEach(type => root.addEventListener(type, isolate));

    pill.addEventListener("click", () => setOpen(true));
    panel.addEventListener("click", async event => {
        const action = event.target.closest("button")?.dataset.action;
        if (!action) return;
        const probe = window[GLOBAL_NAME];
        output.hidden = true;

        if (action === "close") return setOpen(false);
        if (action === "reset") {
            const status = probe.reset();
            result.textContent = `Capture reset. events: ${status.eventCount}, samples: ${status.sampleCount}`;
            return;
        }
        if (action === "status") {
            result.textContent = JSON.stringify(probe.status(), null, 2);
            return;
        }
        if (action === "summary") {
            result.textContent = summaryText(probe.getSummary());
            return;
        }

        const file = traceFile(label.value);
        if (action === "copy") {
            if (await copyTrace(file.json)) {
                result.textContent = `Copied ${file.name}`;
            } else {
                result.textContent = showTextFallback(output, file.json, "Clipboard unavailable.");
            }
            return;
        }

        try {
            const sharedFile = typeof File === "function"
                ? new File([file.blob], file.name, { type: "application/json" })
                : null;
            const shareData = sharedFile ? { files: [sharedFile], title: file.name } : null;
            if (!navigator.share || !shareData || !navigator.canShare?.(shareData)) {
                throw new Error("File sharing unavailable");
            }
            await navigator.share(shareData);
            result.textContent = `Shared ${file.name}`;
        } catch (error) {
            if (error?.name === "AbortError") {
                result.textContent = "Share cancelled.";
                return;
            }
            if (await copyTrace(file.json)) {
                result.textContent = `File sharing unavailable. Copied ${file.name}`;
                return;
            }
            try {
                downloadTrace(file);
                result.textContent = `Download requested: ${file.name}`;
            } catch {
                result.textContent = showTextFallback(output, file.json, "Share and download unavailable.");
            }
        }
    });

    document.body.appendChild(root);
    return () => root.remove();
}
