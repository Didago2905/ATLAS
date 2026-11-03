// Deliberately independent of storage, console output, and gesture probes.
const finite = value => typeof value === "number" && Number.isFinite(value) ? value : null;
const text = value => typeof value === "string" && value ? value.slice(0, 200) : null;

export function collectIssueSnapshot() {
    const ua = navigator.userAgent || "";
    const browser = [/(Edg|EdgiOS|EdgA)\/([\d.]+)/, /(OPR)\/([\d.]+)/,
        /(CriOS|FxiOS|Firefox|Chrome)\/([\d.]+)/, /(Version)\/([\d.]+).*Safari/]
        .map(pattern => ua.match(pattern)).find(Boolean);
    const browserNames = { Edg: "Edge", EdgiOS: "Edge", EdgA: "Edge", OPR: "Opera", CriOS: "Chrome", FxiOS: "Firefox", Version: "Safari" };
    const os = /iPhone|iPad|iPod/.test(ua) ? "iOS/iPadOS"
        : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows"
            : /Macintosh|Mac OS X/.test(ua) ? "macOS (iPadOS posible)"
                : /Linux/.test(ua) ? "Linux" : null;
    const visual = window.visualViewport;
    const connection = navigator.connection;
    let timezone = null;
    try { timezone = text(Intl.DateTimeFormat().resolvedOptions().timeZone); } catch { /* optional */ }
    return {
        schemaVersion: 1,
        timestamp: new Date().toISOString(),
        timezone,
        utcOffsetMinutes: -new Date().getTimezoneOffset(),
        route: window.location.pathname,
        browser: browser ? { name: browserNames[browser[1]] || browser[1], version: text(browser[2]) } : null,
        os,
        viewport: { width: finite(window.innerWidth), height: finite(window.innerHeight) },
        screen: { width: finite(window.screen?.width), height: finite(window.screen?.height) },
        visualViewport: visual ? {
            width: finite(visual.width), height: finite(visual.height),
            offsetTop: finite(visual.offsetTop), offsetLeft: finite(visual.offsetLeft), scale: finite(visual.scale),
        } : null,
        devicePixelRatio: finite(window.devicePixelRatio),
        orientation: text(window.screen?.orientation?.type),
        online: typeof navigator.onLine === "boolean" ? navigator.onLine : null,
        network: connection ? {
            type: text(connection.type), effectiveType: text(connection.effectiveType),
            downlinkMbps: finite(connection.downlink), rttMs: finite(connection.rtt),
            saveData: typeof connection.saveData === "boolean" ? connection.saveData : null,
        } : null,
    };
}
