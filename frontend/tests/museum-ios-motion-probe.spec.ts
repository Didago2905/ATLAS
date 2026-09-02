import { test as base, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import BrowserStackLocal from "browserstack-local";

type GestureOptions = {
    displacement: number;
    durationMs: number;
    steps?: number;
};

type ProbeTrace = {
    metadata: Record<string, unknown>;
    events: Array<Record<string, any>>;
    samples: Array<Record<string, any>>;
    summary: Record<string, any>;
};

const stageSelector = "[data-atlas-museum-stage]";
const resultsDirectory = path.resolve("tests", "results", "ios-motion-probe");
const useLegacyBrowserStack = process.env.ATLAS_BS_LEGACY === "1";

const readBrowserStackValue = (name: string) => {
    const config = fs.readFileSync(path.resolve("browserstack.yml"), "utf8");
    const match = config.match(new RegExp(`^${name}:\\s*([^#\\r\\n]+)`, "m"));
    return match?.[1]?.trim().replace(/^['"]|['"]$/g, "") || "";
};

const browserStackConfig = useLegacyBrowserStack ? {
    userName: process.env.BROWSERSTACK_USERNAME ||
        readBrowserStackValue("userName"),
    accessKey: process.env.BROWSERSTACK_ACCESS_KEY ||
        readBrowserStackValue("accessKey"),
} : null;

const test = base.extend<{
    browserStackLocal: BrowserStackLocal.Local | null;
}>({
    browserStackLocal: [async ({}, use) => {
        if (!useLegacyBrowserStack) {
            await use(null);
            return;
        }

        const local = new BrowserStackLocal.Local();
        await new Promise<void>((resolve, reject) => {
            local.start({
                key: browserStackConfig.accessKey,
                forceLocal: true,
            }, error => error ? reject(error) : resolve());
        });

        try {
            await use(local);
        } finally {
            await new Promise<void>((resolve, reject) => {
                local.stop(error => error ? reject(error) : resolve());
            });
        }
    }, { scope: "worker", timeout: 120_000 }],

    page: async ({ page, playwright, browserStackLocal }, use, testInfo) => {
        if (!useLegacyBrowserStack) {
            await use(page);
            return;
        }

        if (!browserStackLocal) {
            throw new Error("BrowserStack Local did not start");
        }

        const capabilities = {
            browserName: "safari",
            deviceName: "iPhone 15",
            osVersion: "17",
            realMobile: "true",
            deviceOrientation: "landscape",
            name: testInfo.title,
            build: "ATLAS Museum iOS Motion Probe",
            "browserstack.username": browserStackConfig.userName,
            "browserstack.accessKey": browserStackConfig.accessKey,
            "browserstack.local": true,
        };
        const remoteBrowser = await playwright.webkit.connect({
            wsEndpoint:
                "wss://cdp.browserstack.com/playwright?caps=" +
                encodeURIComponent(JSON.stringify(capabilities)),
        });
        const remoteContext = await remoteBrowser.newContext({
            baseURL: "http://bs-local.com:3000",
        });
        const remotePage = await remoteContext.newPage();

        try {
            await use(remotePage);
        } finally {
            await remotePage.close();
            await remoteBrowser.close();
        }
    },
});

const eventCount = (trace: ProbeTrace, type: string) =>
    trace.events.filter(event => event.type === type).length;

const percentile = (values: number[], ratio: number) => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.min(
        sorted.length - 1,
        Math.floor(sorted.length * ratio)
    )];
};

const median = (values: number[]) => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
        ? sorted[middle]
        : (sorted[middle - 1] + sorted[middle]) / 2;
};

function analyzeTrace(trace: ProbeTrace) {
    const frameDeltas = trace.samples
        .map(sample => sample.frameDelta)
        .filter((value): value is number => Number.isFinite(value));
    const velocities = trace.samples
        .map(sample => Math.abs(sample.velocity))
        .filter((value): value is number => Number.isFinite(value));
    const finalSample = trace.samples[trace.samples.length - 1] || null;
    const touchStart = trace.events.find(event => event.type === "touch:start");
    const touchEnd = [...trace.events]
        .reverse()
        .find(event => event.type === "touch:end");
    const clicks = trace.events.filter(event => event.type === "click");
    const centerRequests = trace.events.filter(
        event => event.type === "navigation:center-request"
    );

    const thresholdStats = [20, 25, 33.3, 50].map(threshold => {
        const count = frameDeltas.filter(delta => delta > threshold).length;
        return {
            threshold,
            count,
            percentage: frameDeltas.length ? count / frameDeltas.length * 100 : 0,
        };
    });

    const longFrameClusters: Array<Record<string, any>> = [];
    let currentCluster: Array<Record<string, any>> = [];

    for (const sample of trace.samples) {
        if (Number.isFinite(sample.frameDelta) && sample.frameDelta > 33.3) {
            currentCluster.push({
                t: sample.t,
                frameDelta: sample.frameDelta,
                touching: sample.touching,
                velocity: sample.velocity,
                pendingCenterRequestId: sample.pendingCenterRequestId,
            });
        } else if (currentCluster.length) {
            longFrameClusters.push({
                length: currentCluster.length,
                start: currentCluster[0].t,
                end: currentCluster[currentCluster.length - 1].t,
                maxDelta: Math.max(...currentCluster.map(sample => sample.frameDelta)),
                samples: currentCluster,
            });
            currentCluster = [];
        }
    }

    if (currentCluster.length) {
        longFrameClusters.push({
            length: currentCluster.length,
            start: currentCluster[0].t,
            end: currentCluster[currentCluster.length - 1].t,
            maxDelta: Math.max(...currentCluster.map(sample => sample.frameDelta)),
            samples: currentCluster,
        });
    }

    const centerRequestDetails = centerRequests.map(request => {
        const click = [...clicks]
            .reverse()
            .find(candidate => candidate.t <= request.t);
        const scrollBefore = [...trace.events]
            .reverse()
            .find(event => event.type === "scroll" && event.t <= request.t);
        const scrollAfter = trace.events.find(
            event => event.type === "scroll" && event.t > request.t
        );

        return {
            requestId: request.id,
            t: request.t,
            msSinceTouchEnd: request.msSinceTouchEnd,
            msSinceClick: click ? request.t - click.t : null,
            scrollLeft: request.scrollLeft,
            velocity: request.velocity,
            scrollBeforeDelta: scrollBefore ? request.t - scrollBefore.t : null,
            scrollAfterDelta: scrollAfter ? scrollAfter.t - request.t : null,
            scrollAppearedActive:
                Boolean(scrollBefore && request.t - scrollBefore.t <= 150) ||
                Boolean(scrollAfter && scrollAfter.t - request.t <= 150),
        };
    });

    return {
        counts: {
            touchStart: eventCount(trace, "touch:start"),
            touchMove: eventCount(trace, "touch:move"),
            touchEnd: eventCount(trace, "touch:end"),
            touchCancel: eventCount(trace, "touch:cancel"),
            click: clicks.length,
            scroll: eventCount(trace, "scroll"),
            navigationCenterRequest: centerRequests.length,
            navigationCenterStart: eventCount(trace, "navigation:center-start"),
            selectionChange: eventCount(trace, "selection:change"),
            nativeScrollEnd: eventCount(trace, "scrollend"),
            diagnosticSettled: eventCount(trace, "settled"),
        },
        touchDisplacement:
            touchStart && touchEnd &&
            Number.isFinite(touchStart.x) && Number.isFinite(touchEnd.x)
                ? touchEnd.x - touchStart.x
                : null,
        touchDuration:
            touchStart && touchEnd ? touchEnd.t - touchStart.t : null,
        clicksAfterTouchEnd: clicks.map(click => ({
            t: click.t,
            cardId: click.cardId,
            msSinceTouchEnd: click.msSinceTouchEnd,
            scrollLeft: click.scrollLeft,
            velocity: click.velocity,
        })),
        centerRequestDetails,
        settlementDurationFromLastTouchEnd:
            trace.summary.settlementDurationFromLastTouchEnd ?? null,
        final: finalSample ? {
            t: finalSample.t,
            scrollLeft: finalSample.scrollLeft,
            nearestCardId: finalSample.nearestCardId,
            layoutCenterDelta: finalSample.layoutCenterDelta,
            visualCenterDelta: finalSample.visualCenterDelta,
            velocity: finalSample.velocity,
        } : null,
        frames: {
            sampleCount: trace.samples.length,
            measuredDeltaCount: frameDeltas.length,
            average: frameDeltas.length
                ? frameDeltas.reduce((sum, value) => sum + value, 0) /
                    frameDeltas.length
                : null,
            median: median(frameDeltas),
            p95: percentile(frameDeltas, 0.95),
            maximum: frameDeltas.length ? Math.max(...frameDeltas) : null,
            maximumAbsoluteVelocity: velocities.length
                ? Math.max(...velocities)
                : null,
            thresholds: thresholdStats,
            longFrameClusters,
        },
    };
}

async function waitForProbe(page: Page) {
    await page.waitForFunction(() =>
        Boolean((window as any).__ATLAS_MUSEUM_MOTION_PROBE__)
    );
}

async function resetProbe(page: Page) {
    await page.evaluate(() => {
        (window as any).__ATLAS_MUSEUM_MOTION_PROBE__.reset();
    });
}

async function waitForSettlement(page: Page, timeout = 10_000) {
    try {
        await page.waitForFunction(() => {
            const summary = (window as any)
                .__ATLAS_MUSEUM_MOTION_PROBE__?.getSummary();
            return summary?.settledAt !== null && summary?.sampling === false;
        }, undefined, { timeout });
        return true;
    } catch {
        await page.waitForTimeout(750);
        return false;
    }
}

async function readTrace(page: Page): Promise<ProbeTrace> {
    return page.evaluate(() =>
        (window as any).__ATLAS_MUSEUM_MOTION_PROBE__.getTrace()
    );
}

async function saveExperiment(
    page: Page,
    name: string,
    input: Record<string, unknown>,
    settledByProbe: boolean
) {
    const trace = await readTrace(page);
    const artifact = {
        experiment: name,
        input,
        settledByProbe,
        analysis: analyzeTrace(trace),
        trace,
    };

    fs.mkdirSync(resultsDirectory, { recursive: true });
    fs.writeFileSync(
        path.join(resultsDirectory, `ios-motion-${name}.json`),
        JSON.stringify(artifact, null, 2),
        "utf8"
    );

    return artifact;
}

async function performHorizontalGesture(page: Page, options: GestureOptions) {
    const stage = page.locator(stageSelector);
    const box = await stage.boundingBox();
    if (!box) throw new Error("Museum stage has no interaction geometry");

    const direction = Math.sign(options.displacement) || -1;
    const travel = Math.min(Math.abs(options.displacement), box.width * 0.7);
    const startX = direction < 0
        ? box.x + box.width * 0.82
        : box.x + box.width * 0.18;
    const endX = startX + direction * travel;
    const y = box.y + box.height * 0.58;
    const steps = options.steps ?? 8;

    try {
        await page.mouse.move(startX, y);
        await page.mouse.down();

        for (let step = 1; step <= steps; step += 1) {
            const progress = step / steps;
            await page.mouse.move(
                startX + (endX - startX) * progress,
                y
            );
            await page.waitForTimeout(options.durationMs / steps);
        }

        await page.mouse.up();

        return {
            supported: true,
            requestedDisplacement: endX - startX,
            durationMs: options.durationMs,
            steps,
            startX,
            endX,
            y,
        };
    } catch (error) {
        return {
            supported: false,
            requestedDisplacement: endX - startX,
            durationMs: options.durationMs,
            steps,
            startX,
            endX,
            y,
            limitation: error instanceof Error ? error.message : String(error),
        };
    }
}

async function positionForOffCenterTap(page: Page) {
    return page.locator(stageSelector).evaluate(stage => {
        const cards = Array.from(
            stage.querySelectorAll<HTMLElement>("[data-atlas-museum-card]")
        );
        const candidates = cards.map(card => {
            const rect = card.getBoundingClientRect();
            const stageRect = stage.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const delta = rect.left + rect.width / 2 -
                (stageRect.left + stage.clientWidth / 2);
            return { card, rect, stageRect, centerX, delta };
        }).filter(candidate =>
            Math.abs(candidate.delta) > 10 &&
            candidate.centerX >= candidate.stageRect.left + 8 &&
            candidate.centerX <= candidate.stageRect.right - 8
        ).sort((left, right) =>
            Math.abs(right.delta) - Math.abs(left.delta)
        );

        const candidate = candidates[0];

        if (!candidate) return null;

        const { card: target, rect } = candidate;
        return {
            cardId: target.dataset.atlasMuseumCardId,
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
            visualDeltaBeforeTap:
                rect.left + rect.width / 2 - window.innerWidth / 2,
        };
    });
}

test("ATLAS Museum iOS motion probe diagnostics", async ({ page }) => {
    test.setTimeout(6 * 60_000);

    await page.goto("/museum?motionProbe=1");
    const stage = page.locator(stageSelector);
    await expect(stage).toBeVisible();
    await waitForProbe(page);
    await expect.poll(async () => page.locator(
        "[data-atlas-museum-card]"
    ).count()).toBeGreaterThan(1);

    const environment = await page.evaluate(() => ({
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        devicePixelRatio: window.devicePixelRatio,
        visualViewport: window.visualViewport ? {
            width: window.visualViewport.width,
            height: window.visualViewport.height,
            scale: window.visualViewport.scale,
        } : null,
    }));

    const artifacts: Array<Record<string, any>> = [];

    await resetProbe(page);
    const longInput = await performHorizontalGesture(page, {
        displacement: -520,
        durationMs: 420,
        steps: 14,
    });
    artifacts.push(await saveExperiment(
        page,
        "long-swipe",
        longInput,
        longInput.supported ? await waitForSettlement(page) : false
    ));

    await resetProbe(page);
    const shortInput = await performHorizontalGesture(page, {
        displacement: -230,
        durationMs: 260,
        steps: 8,
    });
    artifacts.push(await saveExperiment(
        page,
        "short-swipe",
        shortInput,
        shortInput.supported ? await waitForSettlement(page) : false
    ));

    await resetProbe(page);
    const microInput = await performHorizontalGesture(page, {
        displacement: -10,
        durationMs: 140,
        steps: 3,
    });
    artifacts.push(await saveExperiment(
        page,
        "micro-swipe",
        microInput,
        microInput.supported ? await waitForSettlement(page) : false
    ));

    const offCenterTarget = await positionForOffCenterTap(page);
    expect(offCenterTarget, "Expected a visible off-center card").toBeTruthy();
    await resetProbe(page);
    await page.touchscreen.tap(offCenterTarget!.x, offCenterTarget!.y);
    artifacts.push(await saveExperiment(
        page,
        "offcenter-tap",
        offCenterTarget!,
        await waitForSettlement(page)
    ));

    await resetProbe(page);
    const rapidInputs = [];
    for (let index = 0; index < 3; index += 1) {
        const rapidInput = await performHorizontalGesture(page, {
            displacement: -260,
            durationMs: 150,
            steps: 5,
        });
        rapidInputs.push(rapidInput);
        if (!rapidInput.supported) break;
        await page.waitForTimeout(120);
    }
    artifacts.push(await saveExperiment(
        page,
        "rapid-swipes",
        { gestures: rapidInputs },
        rapidInputs.every(input => input.supported)
            ? await waitForSettlement(page, 12_000)
            : false
    ));

    await resetProbe(page);
    const proximityInput = await performHorizontalGesture(page, {
        displacement: -300,
        durationMs: 300,
        steps: 10,
    });
    artifacts.push(await saveExperiment(
        page,
        "snap-settlement",
        proximityInput,
        proximityInput.supported
            ? await waitForSettlement(page, 12_000)
            : false
    ));

    fs.writeFileSync(
        path.join(resultsDirectory, "ios-motion-comparison.json"),
        JSON.stringify({
            capturedAt: new Date().toISOString(),
            environment,
            experiments: artifacts.map(artifact => ({
                experiment: artifact.experiment,
                input: artifact.input,
                settledByProbe: artifact.settledByProbe,
                analysis: artifact.analysis,
            })),
        }, null, 2),
        "utf8"
    );

    console.log("MUSEUM IOS MOTION PROBE RESULTS");
    console.log(JSON.stringify({
        environment,
        experiments: artifacts.map(artifact => ({
            experiment: artifact.experiment,
            analysis: artifact.analysis,
        })),
    }, null, 2));

    const offCenterTapArtifact = artifacts.find(
        artifact => artifact.experiment === "offcenter-tap"
    );
    expect(offCenterTapArtifact?.analysis.counts.touchStart).toBeGreaterThan(0);
    expect(offCenterTapArtifact?.analysis.counts.touchEnd).toBeGreaterThan(0);
    expect(offCenterTapArtifact?.analysis.counts.click).toBeGreaterThan(0);
});
