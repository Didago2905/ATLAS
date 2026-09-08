import { test, expect, type Page } from "@playwright/test";

const beer = {
    id: 1,
    name: "Gesture Test Beer",
    style: "Test Style",
    abv: 5,
    tap_position: 1,
    is_featured: false,
    image_url: "",
};

async function openTapGrid(page: Page, path = "/") {
    await page.route("**/api/public/tap", (route) =>
        route.fulfill({ json: [beer] })
    );
    await page.route("**/api/audit/**", (route) =>
        route.fulfill({ status: 204 })
    );
    await page.goto(path);
    await expect(page.locator("[data-atlas-tap-card]"))
        .toHaveCount(1);
}

async function dispatchTouch(page: Page, type: string, touchCount: number) {
    await page.evaluate(({ eventType, count }) => {
        const event = new Event(eventType, {
            bubbles: true,
            cancelable: true,
        });
        Object.defineProperty(event, "touches", {
            value: Array.from({ length: count }, (_, identifier) => ({ identifier })),
        });
        Object.defineProperty(event, "changedTouches", {
            value: Array.from({ length: count }, (_, identifier) => ({ identifier })),
        });
        window.dispatchEvent(event);
    }, { eventType: type, count: touchCount });
}

async function dispatchRawTouch(
    page: Page,
    type: string,
    touchIdentifiers: number[],
    changedIdentifiers: number[]
) {
    await page.evaluate(({ eventType, touches, changedTouches }) => {
        const event = new Event(eventType, { bubbles: true, cancelable: true });
        const point = (identifier: number) => ({
            identifier,
            clientX: 100 + identifier,
            clientY: 200 + identifier,
            pageX: 300 + identifier,
            pageY: 400 + identifier,
            screenX: 500 + identifier,
            screenY: 600 + identifier,
        });
        Object.defineProperty(event, "touches", { value: touches.map(point) });
        Object.defineProperty(event, "changedTouches", { value: changedTouches.map(point) });
        window.dispatchEvent(event);
    }, { eventType: type, touches: touchIdentifiers, changedTouches: changedIdentifiers });
}

test("a normal card click still opens BeerDetail", async ({ page }) => {
    await openTapGrid(page);

    await page.locator("[data-atlas-tap-card]").click();

    await expect(page).toHaveURL(/\/beer\/1$/);
});

test("multitouch evidence suppresses a residual card click", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 1);
    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await page.locator("[data-atlas-tap-card]").click();
    await page.waitForTimeout(300);

    await expect(page).toHaveURL(/\/$/);
});

test("recognized two-finger double tap toggles mode without navigation", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("tap_grid_mode")
    )).toBe("gallery");

    await page.locator("[data-atlas-tap-card]").click();
    await page.waitForTimeout(300);

    await expect(page).toHaveURL(/\/$/);
});

test("touchcancel clears the guard for the next normal activation", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchcancel", 0);
    await page.locator("[data-atlas-tap-card]").click();

    await expect(page).toHaveURL(/\/beer\/1$/);
});

test("completed multitouch guard expires before a later normal activation", async ({ page }) => {
    await openTapGrid(page);

    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await page.waitForTimeout(375);
    await page.locator("[data-atlas-tap-card]").click();

    await expect(page).toHaveURL(/\/beer\/1$/);
});

test("timing lab is absent without its query flag", async ({ page }) => {
    await openTapGrid(page);

    await expect(page.getByText("CHORD→CHORD")).toHaveCount(0);
    await expect.poll(() => page.evaluate(() =>
        "ATLAS_TAP_TIMING_LAB" in window
    )).toBe(false);
});

test("timing lab reports chord, release, and productive decision timing", async ({ page }) => {
    await openTapGrid(page, "/?tapTimingLab=1");

    await dispatchTouch(page, "touchstart", 2);
    await dispatchTouch(page, "touchend", 0);
    await page.waitForTimeout(25);
    await dispatchTouch(page, "touchstart", 2);

    const result = await page.evaluate(() => {
        const lab = (window as typeof window & {
            ATLAS_TAP_TIMING_LAB: {
                getTrace: () => Array<{ type: string }>;
                getSummary: () => {
                    lastAttempt: {
                        chordToChordMs: number;
                        releaseToSecondChordMs: number;
                        firstChordToReleaseMs: number;
                        toggleRecognized: boolean;
                    };
                };
                exportTrace: () => string;
            };
        }).ATLAS_TAP_TIMING_LAB;
        return {
            traceTypes: lab.getTrace().map(entry => entry.type),
            summary: lab.getSummary(),
            exported: JSON.parse(lab.exportTrace()),
        };
    });

    expect(result.traceTypes).toEqual([
        "TOUCHSTART", "TWO_FINGER_CHORD", "NEW_PHYSICAL_CHORD", "PRODUCTIVE_DECISION",
        "TOUCHEND", "FULL_RELEASE",
        "TOUCHSTART", "TWO_FINGER_CHORD", "NEW_PHYSICAL_CHORD", "PRODUCTIVE_DECISION",
    ]);
    expect(result.summary.lastAttempt.chordToChordMs).toBeGreaterThan(0);
    expect(result.summary.lastAttempt.releaseToSecondChordMs).toBeGreaterThan(0);
    expect(result.summary.lastAttempt.firstChordToReleaseMs).toBeGreaterThanOrEqual(0);
    expect(result.summary.lastAttempt.toggleRecognized).toBe(true);
    expect(result.exported.summary.lastAttempt.toggleRecognized).toBe(true);
    await expect(page.getByText("TOGGLE YES")).toBeVisible();
    await expect(page).toHaveURL(/\/?tapTimingLab=1$/);
});

test("timing lab preserves chronological raw touch data and decision correlation", async ({ page }) => {
    await openTapGrid(page, "/?tapTimingLab=1");

    await dispatchRawTouch(page, "touchstart", [4, 7], [4, 7]);
    await dispatchRawTouch(page, "touchend", [4], [7]);
    await dispatchRawTouch(page, "touchstart", [4, 8], [8]);
    await dispatchRawTouch(page, "touchcancel", [], [4, 8]);

    const trace = await page.evaluate(() =>
        (window as typeof window & {
            ATLAS_TAP_TIMING_LAB: { getTrace: () => Array<Record<string, unknown>> };
        }).ATLAS_TAP_TIMING_LAB.getTrace()
    );
    const raw = trace.filter(entry => entry.raw) as Array<{
        type: string;
        eventType: string;
        sequence: number;
        eventTimeStamp: number;
        dateNowRelativeMs: number;
        touchesLength: number;
        changedTouchesLength: number;
        touches: Array<{ identifier: number; clientX: number; screenY: number }>;
        changedTouches: Array<{ identifier: number; pageX: number }>;
    }>;
    const decisions = trace.filter(entry => entry.type === "PRODUCTIVE_DECISION") as Array<{
        rawEventSequence: number;
    }>;

    expect(raw.map(entry => entry.eventType)).toEqual([
        "touchstart", "touchend", "touchstart", "touchcancel",
    ]);
    expect(raw.map(entry => entry.sequence)).toEqual([1, 2, 3, 4]);
    expect(raw[1].touchesLength).toBe(1);
    expect(raw[1].changedTouchesLength).toBe(1);
    expect(raw[0].touches.map(touch => touch.identifier)).toEqual([4, 7]);
    expect(raw[1].changedTouches.map(touch => touch.identifier)).toEqual([7]);
    expect(raw[2].touches.map(touch => touch.identifier)).toEqual([4, 8]);
    expect(raw[0].touches[0]).toMatchObject({ clientX: 104, screenY: 604 });
    expect(raw[1].changedTouches[0]).toMatchObject({ pageX: 307 });
    expect(raw.every(entry => typeof entry.eventTimeStamp === "number")).toBe(true);
    expect(raw.every(entry => typeof entry.dateNowRelativeMs === "number")).toBe(true);
    expect(decisions.map(entry => entry.rawEventSequence)).toEqual([1, 3]);
});

test("timing lab panel copies active views and exports complete JSON sessions", async ({ page }) => {
    await page.addInitScript(() => {
        const testWindow = window as typeof window & {
            __copied: string[];
            __exports: Array<{ blob: Blob; name: string }>;
        };
        testWindow.__copied = [];
        testWindow.__exports = [];
        Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: { writeText: async (text: string) => testWindow.__copied.push(text) },
        });
        URL.createObjectURL = (blob: Blob) => {
            testWindow.__exports.push({ blob, name: "" });
            return "blob:atlas-timing-test";
        };
        URL.revokeObjectURL = () => {};
        HTMLAnchorElement.prototype.click = function () {
            testWindow.__exports.at(-1)!.name = this.download;
        };
    });
    await openTapGrid(page, "/?tapTimingLab=1");

    const panelView = page.locator("[data-atlas-timing-view]");
    await expect(panelView).toHaveAttribute("data-atlas-timing-view", "summary");
    await page.getByRole("button", { name: "COPY", exact: true }).click();

    await dispatchRawTouch(page, "touchstart", [4, 7], [4, 7]);
    await dispatchRawTouch(page, "touchend", [4], [7]);
    await dispatchRawTouch(page, "touchstart", [4, 8], [8]);
    await page.getByRole("button", { name: "RAW", exact: true }).click();
    await expect(panelView).toHaveAttribute("data-atlas-timing-view", "raw");
    await expect(panelView).toContainText('"identifier": 8');
    await expect(panelView).toContainText('"rawEventSequence": 3');
    await page.getByRole("button", { name: "COPY", exact: true }).click();
    await page.getByRole("button", { name: "EXPORT JSON", exact: true }).click();

    const captured = await page.evaluate(async () => {
        const testWindow = window as typeof window & {
            __copied: string[];
            __exports: Array<{ blob: Blob; name: string }>;
        };
        return {
            copied: testWindow.__copied.map(JSON.parse),
            exported: JSON.parse(await testWindow.__exports[0].blob.text()),
            filename: testWindow.__exports[0].name,
        };
    });
    expect(captured.copied[0]).toMatchObject({ attempts: [], lastAttempt: null });
    expect(captured.copied[1].map((entry: { type: string }) => entry.type)).toEqual([
        "TOUCHSTART", "TWO_FINGER_CHORD", "NEW_PHYSICAL_CHORD", "PRODUCTIVE_DECISION",
        "TOUCHEND", "TOUCHSTART", "TWO_FINGER_CHORD", "NEW_PHYSICAL_CHORD",
        "PRODUCTIVE_DECISION",
    ]);
    expect(captured.exported).toMatchObject({
        meta: { lab: "ATLAS_TAP_TIMING_LAB", version: 1, thresholdMs: 350 },
    });
    expect(captured.exported.summary.attempts).toHaveLength(1);
    const thirdRawEvent = captured.exported.trace.find(
        (entry: { raw: boolean; sequence: number }) => entry.raw && entry.sequence === 3
    );
    expect(thirdRawEvent.touches.map(
        (touch: { identifier: number }) => touch.identifier
    )).toEqual([4, 8]);
    expect(captured.filename).toMatch(/^atlas-tap-timing-.+\.json$/);

    await page.getByRole("button", { name: "RESET", exact: true }).click();
    await page.getByRole("button", { name: "EXPORT JSON", exact: true }).click();
    const resetExport = await page.evaluate(async () => {
        const exported = (window as typeof window & {
            __exports: Array<{ blob: Blob }>;
        }).__exports[1];
        return JSON.parse(await exported.blob.text());
    });
    expect(resetExport.summary).toEqual({ attempts: [], lastAttempt: null });
    expect(resetExport.trace).toEqual([]);
});

test("timing lab reports clipboard failure without breaking the panel", async ({ page }) => {
    await page.addInitScript(() => {
        Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: { writeText: async () => { throw new Error("denied"); } },
        });
    });
    await openTapGrid(page, "/?tapTimingLab=1");

    await page.getByRole("button", { name: "COPY", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("COPY FAILED");
    await expect(page.getByRole("button", { name: "RAW", exact: true })).toBeVisible();
});

test("same and reordered identifier sets are coalesced without toggling", async ({ page }) => {
    await openTapGrid(page);

    await dispatchRawTouch(page, "touchstart", [1, 2], [1]);
    await dispatchRawTouch(page, "touchstart", [1, 2], [2]);
    await dispatchRawTouch(page, "touchstart", [2, 1], [2]);

    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("tap_grid_mode")
    )).toBe("focus");
});

test("a new identifier set toggles once and its duplicates are coalesced", async ({ page }) => {
    await openTapGrid(page);

    await dispatchRawTouch(page, "touchstart", [1, 2], [1, 2]);
    await dispatchRawTouch(page, "touchstart", [3, 4], [3, 4]);
    await dispatchRawTouch(page, "touchstart", [4, 3], [4]);

    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("tap_grid_mode")
    )).toBe("gallery");
});

test("a new identifier set after 350ms does not toggle", async ({ page }) => {
    await openTapGrid(page);

    await dispatchRawTouch(page, "touchstart", [1, 2], [1, 2]);
    await page.waitForTimeout(375);
    await dispatchRawTouch(page, "touchstart", [3, 4], [3, 4]);

    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("tap_grid_mode")
    )).toBe("focus");
});

test("touchcancel clears chord identity and a later complete gesture works", async ({ page }) => {
    await openTapGrid(page, "/?tapTimingLab=1");

    await dispatchRawTouch(page, "touchstart", [1, 2], [1, 2]);
    await dispatchRawTouch(page, "touchcancel", [], [1, 2]);
    await page.waitForTimeout(375);
    await dispatchRawTouch(page, "touchstart", [1, 2], [1, 2]);
    await dispatchRawTouch(page, "touchend", [], [1, 2]);
    await dispatchRawTouch(page, "touchstart", [3, 4], [3, 4]);

    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("tap_grid_mode")
    )).toBe("gallery");
    const classifications = await page.evaluate(() =>
        (window as typeof window & {
            ATLAS_TAP_TIMING_LAB: { getTrace: () => Array<{ type: string }> };
        }).ATLAS_TAP_TIMING_LAB.getTrace()
            .filter(entry => entry.type.endsWith("PHYSICAL_CHORD"))
            .map(entry => entry.type)
    );
    expect(classifications).toEqual([
        "NEW_PHYSICAL_CHORD", "NEW_PHYSICAL_CHORD", "NEW_PHYSICAL_CHORD",
    ]);
});

test("timing lab records normalized new and same physical chord decisions", async ({ page }) => {
    await openTapGrid(page, "/?tapTimingLab=1");

    await dispatchRawTouch(page, "touchstart", [2, 1], [1]);
    await dispatchRawTouch(page, "touchstart", [1, 2], [2]);

    const result = await page.evaluate(() => {
        const trace = (window as typeof window & {
            ATLAS_TAP_TIMING_LAB: { getTrace: () => Array<Record<string, unknown>> };
        }).ATLAS_TAP_TIMING_LAB.getTrace();
        return {
            classifications: trace.filter(entry => entry.type === "NEW_PHYSICAL_CHORD"
                || entry.type === "SAME_PHYSICAL_CHORD"),
            productiveDecisions: trace.filter(entry => entry.type === "PRODUCTIVE_DECISION"),
        };
    });
    expect(result.classifications).toMatchObject([
        { type: "NEW_PHYSICAL_CHORD", identifiers: [1, 2], rawEventSequence: 1 },
        { type: "SAME_PHYSICAL_CHORD", identifiers: [1, 2], rawEventSequence: 2 },
    ]);
    expect(result.productiveDecisions).toHaveLength(1);
});
