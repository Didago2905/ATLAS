import { useEffect, useState } from "react";

const value = number => number === null || number === undefined ? "—" : `${number} ms`;

export default function TapTimingLabPanel({ lab }) {
    const [, refresh] = useState(0);
    const [activeView, setActiveView] = useState("summary");
    const [copyStatus, setCopyStatus] = useState("");

    useEffect(() => lab.subscribe(() => refresh(count => count + 1)), [lab]);

    const summary = lab.getSummary();
    const last = summary.lastAttempt;

    const visibleData = activeView === "raw" ? lab.getTrace() : summary;

    const reset = () => {
        lab.reset();
        setCopyStatus("");
    };

    const copy = async () => {
        if (!navigator.clipboard?.writeText) {
            setCopyStatus("CLIPBOARD UNAVAILABLE");
            return;
        }
        try {
            await navigator.clipboard.writeText(JSON.stringify(visibleData, null, 2));
            setCopyStatus("COPIED");
        } catch {
            setCopyStatus("COPY FAILED");
        }
    };

    const exportJson = () => {
        const json = JSON.stringify(lab.exportSession(), null, 2);
        const blob = new Blob([json], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
        anchor.href = url;
        anchor.download = `atlas-tap-timing-${timestamp}.json`;
        anchor.click();
        URL.revokeObjectURL(url);
    };

    return (
        <aside style={{
            position: "fixed", bottom: 8, left: 8, zIndex: 10000,
            maxWidth: "calc(100vw - 16px)", padding: 10, borderRadius: 8,
            color: "#fff", background: "rgba(0,0,0,.9)", font: "12px monospace",
        }}>
            <div>CHORD→CHORD {value(last?.chordToChordMs)}</div>
            <div>RELEASE→2ND {value(last?.releaseToSecondChordMs)}</div>
            <div>TOGGLE {last?.toggleRecognized ? "YES" : "NO"}</div>
            <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
                <button type="button" onClick={reset}>RESET</button>
                <button type="button" onClick={() => setActiveView("summary")}>SUMMARY</button>
                <button type="button" onClick={() => setActiveView("raw")}>RAW</button>
                <button type="button" onClick={copy}>COPY</button>
                <button type="button" onClick={exportJson}>EXPORT JSON</button>
            </div>
            {copyStatus && <div role="status">{copyStatus}</div>}
            <pre data-atlas-timing-view={activeView} style={{
                maxHeight: 180, overflow: "auto", whiteSpace: "pre-wrap",
            }}>
                {JSON.stringify(visibleData, null, 2)}
            </pre>
        </aside>
    );
}
