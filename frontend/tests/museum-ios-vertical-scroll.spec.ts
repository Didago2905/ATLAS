import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("ATLAS Museum iOS landscape vertical-scroll post-fix", async ({ page }) => {
    test.setTimeout(90_000);

    const stageSelector = "[data-atlas-museum-stage]";
    const trackSelector = "[data-atlas-museum-track]";

    await page.goto("http://bs-local.com:3000/museum");

    const stage = page.locator(stageSelector);
    const track = page.locator(trackSelector);

    await expect(stage).toBeVisible();
    await expect(track).toBeVisible();

    await expect.poll(
        async () =>
            track.evaluate(trackElement =>
                Array.from(trackElement.children).filter(
                    child => child.querySelector("img")
                ).length
            )
    ).toBeGreaterThan(0);

    const readGeometry = async (label: string) => {
        return track.evaluate((trackElement, currentLabel) => {
            const stageElement = trackElement.parentElement;

            if (!stageElement) {
                throw new Error(
                    "Museum stage unavailable from current track"
                );
            }

            const html = document.documentElement;
            const body = document.body;
            const viewport = window.visualViewport;

            const htmlStyle = getComputedStyle(html);
            const bodyStyle = getComputedStyle(body);
            const stageStyle = getComputedStyle(stageElement);
            const trackStyle = getComputedStyle(trackElement);

            const stageRect = stageElement.getBoundingClientRect();
            const trackRect = trackElement.getBoundingClientRect();

            return {
                label: currentLabel,

                orientation:
                    window.innerWidth > window.innerHeight
                        ? "landscape"
                        : "portrait",

                window: {
                    innerWidth: window.innerWidth,
                    innerHeight: window.innerHeight,
                    outerWidth: window.outerWidth,
                    outerHeight: window.outerHeight,
                    scrollX: window.scrollX,
                    scrollY: window.scrollY,
                },

                visualViewport: viewport
                    ? {
                          width: viewport.width,
                          height: viewport.height,
                          offsetLeft: viewport.offsetLeft,
                          offsetTop: viewport.offsetTop,
                          pageLeft: viewport.pageLeft,
                          pageTop: viewport.pageTop,
                          scale: viewport.scale,
                      }
                    : null,

                html: {
                    clientWidth: html.clientWidth,
                    clientHeight: html.clientHeight,
                    scrollWidth: html.scrollWidth,
                    scrollHeight: html.scrollHeight,
                },

                body: {
                    clientWidth: body.clientWidth,
                    clientHeight: body.clientHeight,
                    scrollWidth: body.scrollWidth,
                    scrollHeight: body.scrollHeight,
                    computedMinHeight: bodyStyle.minHeight,
                },

                stage: {
                    offsetWidth: stageElement.offsetWidth,
                    offsetHeight: stageElement.offsetHeight,
                    clientWidth: stageElement.clientWidth,
                    clientHeight: stageElement.clientHeight,
                    scrollWidth: stageElement.scrollWidth,
                    scrollHeight: stageElement.scrollHeight,
                    scrollLeft: stageElement.scrollLeft,
                    scrollTop: stageElement.scrollTop,
                    rect: {
                        top: stageRect.top,
                        bottom: stageRect.bottom,
                        width: stageRect.width,
                        height: stageRect.height,
                    },
                },

                track: {
                    offsetWidth: trackElement.offsetWidth,
                    offsetHeight: trackElement.offsetHeight,
                    clientWidth: trackElement.clientWidth,
                    clientHeight: trackElement.clientHeight,
                    scrollWidth: trackElement.scrollWidth,
                    scrollHeight: trackElement.scrollHeight,
                    rect: {
                        top: trackRect.top,
                        bottom: trackRect.bottom,
                        width: trackRect.width,
                        height: trackRect.height,
                    },
                },

                computed: {
                    htmlOverflowY: htmlStyle.overflowY,
                    bodyOverflowY: bodyStyle.overflowY,
                    bodyMinHeight: bodyStyle.minHeight,
                    stageOverflowX: stageStyle.overflowX,
                    stageOverflowY: stageStyle.overflowY,
                    stageHeight: stageStyle.height,
                    trackHeight: trackStyle.height,
                },

                verticalRanges: {
                    document:
                        Math.max(
                            html.scrollHeight,
                            body.scrollHeight
                        ) - window.innerHeight,

                    html:
                        html.scrollHeight -
                        html.clientHeight,

                    bodyAgainstViewport:
                        body.scrollHeight -
                        window.innerHeight,

                    stage:
                        stageElement.scrollHeight -
                        stageElement.clientHeight,

                    track:
                        trackElement.scrollHeight -
                        trackElement.clientHeight,
                },
            };
        }, label);
    };

    await track.evaluate(() => {
        window.scrollTo(0, 0);
    });

    await page.waitForTimeout(300);

    const before = await readGeometry(
        "production-before-scroll"
    );

    await track.evaluate(() => {
        window.scrollBy(0, 100);
    });

    await page.waitForTimeout(500);

    const afterScroll = await readGeometry(
        "production-after-scrollBy-100"
    );

    await track.evaluate(() => {
        window.scrollTo(0, 0);
    });

    await page.waitForTimeout(300);

    const afterReset = await readGeometry(
        "production-after-reset"
    );

    const artifact = {
        capturedAt: new Date().toISOString(),

        diagnosticPurpose:
            "Verify post-fix Museum document Y reachability on iOS landscape without test-only CSS overrides.",

        snapshots: {
            before,
            afterScroll,
            afterReset,
        },

        comparison: {
            orientation: before.orientation,

            documentVerticalRange:
                Math.max(
                    before.html.scrollHeight,
                    before.body.scrollHeight
                ) - before.window.innerHeight,

            scrollYBefore:
                before.window.scrollY,

            scrollYAfter100:
                afterScroll.window.scrollY,

            visualViewportPageTopBefore:
                before.visualViewport?.pageTop ?? null,

            visualViewportPageTopAfter100:
                afterScroll.visualViewport?.pageTop ?? null,

            stageTopBefore:
                before.stage.rect.top,

            stageTopAfter100:
                afterScroll.stage.rect.top,

            stageHeight:
                before.stage.clientHeight,

            trackHeight:
                before.track.clientHeight,

            stageScrollWidth:
                before.stage.scrollWidth,

            trackScrollWidth:
                before.track.scrollWidth,
        },
    };

    const resultsDirectory = path.resolve(
        "tests",
        "results"
    );

    fs.mkdirSync(resultsDirectory, {
        recursive: true,
    });

    fs.writeFileSync(
        path.join(
            resultsDirectory,
            "museum-ios-landscape-scroll.json"
        ),
        JSON.stringify(artifact, null, 2),
        "utf8"
    );

    console.log(
        "MUSEUM IOS LANDSCAPE POST-FIX DIAGNOSTIC"
    );

    console.log(
        JSON.stringify(artifact, null, 2)
    );

    expect(before.stage.clientHeight)
        .toBeGreaterThan(0);

    expect(before.track.clientHeight)
        .toBeGreaterThan(0);

    expect(before.orientation)
        .toBe("landscape");

    expect(
        Math.max(
            before.html.scrollHeight,
            before.body.scrollHeight
        )
    ).toBeLessThanOrEqual(
        before.window.innerHeight + 1
    );

    expect(afterScroll.window.scrollY)
        .toBe(0);
});