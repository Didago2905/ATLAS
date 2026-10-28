import { test, expect, Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const svg = (width: number, height: number) => `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="gray"/></svg>`)}`;
const records = ["tap_list", "carta_vieja", "carta_nueva", "etiquetas"].flatMap(category =>
    (category === "tap_list" ? [[660, 1000], [713, 1000], [647, 1000]]
        : category === "carta_nueva" ? [[1600, 900], [1535, 827], [2400, 900]]
        : category === "etiquetas" ? [[1200, 900], [3083, 1667], [2400, 600]]
        : [[1600, 900], [1000, 1000], [600, 900]]).map(([width, height], index) => ({
        id: `${category}-${index}`, name: `${category} ${index}`, category,
        image_url: svg(width, height), manifest_metadata: { width: String(width), height: String(height) },
    })));
const labels = ["Tablas", "Cartas Viejas", "Cartas Nuevas", "Etiquetas"];
const categories = ["tap_list", "carta_vieja", "carta_nueva", "etiquetas"];
const card = (page: Page, id: string) => page.locator(`[data-atlas-museum-card-id="${id}"]`);

async function mock(page: Page, items = records) {
    await page.route("**/api/public/museum", route => route.fulfill({ json: items }));
    await page.route("**/api/public/tap", route => route.fulfill({ json: [] }));
}
async function centered(page: Page, id: string) {
    await expect.poll(() => card(page, id).evaluate(node => {
        const stage = document.querySelector("[data-atlas-museum-stage]")!;
        return Math.abs((node as HTMLElement).offsetLeft + (node as HTMLElement).offsetWidth / 2
            - stage.scrollLeft - stage.clientWidth / 2);
    })).toBeLessThanOrEqual(2);
}

for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }, { width: 320, height: 568 }, { width: 568, height: 320 }]) {
    test(`collection geometry, full composition and navigation at ${viewport.width}x${viewport.height}`, async ({ page }) => {
        test.setTimeout(60_000);
        await page.setViewportSize(viewport);
        await mock(page);
        await page.goto("/museum");
        for (let i = 0; i < labels.length; i++) {
            await page.getByRole("button", { name: labels[i], exact: true }).click();
            const slots = page.locator("[data-atlas-museum-card]");
            await expect(slots).toHaveCount(3);
            await expect.poll(() => slots.locator("img").evaluateAll(images => images.every(image => (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
            const measurements = await slots.evaluateAll(nodes => nodes.map(node => {
                const slot = node as HTMLElement, image = node.querySelector("img")!, visual = node.querySelector("[data-atlas-museum-visual]")!;
                const css = getComputedStyle(image), vcss = getComputedStyle(visual);
                return { width: slot.offsetWidth, height: slot.offsetHeight, fit: css.objectFit, position: css.objectPosition,
                    padding: parseFloat(vcss.paddingLeft), margin: vcss.margin, background: vcss.backgroundColor,
                    shadow: vcss.boxShadow, radius: vcss.borderRadius, overflow: vcss.overflow,
                    imageLeft: (visual as HTMLElement).offsetLeft - slot.offsetLeft + image.offsetLeft,
                    imageTop: (visual as HTMLElement).offsetTop - slot.offsetTop + image.offsetTop,
                    imageWidth: image.clientWidth, imageHeight: image.clientHeight,
                    scrollWidth: slot.scrollWidth, aspect: image.naturalWidth / image.naturalHeight };
            }));
            for (const m of measurements) {
                expect(m.fit).toBe("contain");
                expect(m.position).toBe("50% 50%");
                expect(m.padding).toBe(0);
                expect(m.margin).toBe("8px");
                expect(m.background).toBe("rgba(0, 0, 0, 0)");
                expect(m.shadow).toBe("none");
                expect(m.radius).toBe("0px");
                expect(m.overflow).toBe("visible");
                expect(m.imageLeft).toBe(8);
                expect(m.imageTop).toBe(8);
                expect(m.imageWidth).toBeLessThanOrEqual(m.width - 15);
                expect(m.imageHeight).toBeLessThanOrEqual(m.height - 15);
                expect(Math.abs(m.imageWidth - (m.width - 16))).toBeLessThanOrEqual(1);
                expect(Math.abs(m.imageHeight - (m.height - 16))).toBeLessThanOrEqual(1);
                expect(m.scrollWidth).toBeLessThanOrEqual(m.width);
                expect(m.width).toBeLessThanOrEqual(viewport.width - (viewport.width > viewport.height ? 192 : 48) + 1);
                expect(m.height).toBeLessThanOrEqual(Math.min(300, viewport.height - 32) + 1);
                const scale = Math.min(m.imageWidth / m.aspect, m.imageHeight);
                expect(Math.max(m.imageWidth - m.aspect * scale, m.imageHeight - scale)).toBeLessThanOrEqual(1.5);
                if (i === 0) {
                    expect(m.width).toBeLessThanOrEqual(220);
                    expect(m.height).toBeGreaterThan(m.width);
                }
            }
            const first = `${categories[i]}-0`, last = `${categories[i]}-2`;
            await centered(page, first);
            await card(page, last).dispatchEvent("click");
            await centered(page, last);
            await card(page, first).dispatchEvent("click");
            await centered(page, first);
            const stage = page.locator("[data-atlas-museum-stage]");
            const stageBox = await stage.boundingBox();
            if (!stageBox) throw new Error("Missing stage");
            await page.mouse.move(stageBox.x + stageBox.width / 2, stageBox.y + stageBox.height / 2);
            await page.mouse.wheel(500, 0);
            await expect.poll(() => stage.evaluate(node => node.scrollLeft)).toBeGreaterThan(100);
            await page.mouse.wheel(-2000, 0);
            await centered(page, first);
            await card(page, first).click();
            const viewer = page.locator("[data-atlas-museum-artwork-overlay]");
            await expect(viewer).toBeVisible();
            await expect(viewer.locator("img")).toHaveAttribute("src", records.find(r => r.id === first)!.image_url);
            await viewer.click();
            await expect(viewer).toHaveCount(0);
        }
    });
}

test("late legacy image dimensions preserve the already centered artwork", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const items = records.filter(r => r.category === "carta_vieja").map((r, i) => i === 0
        ? { id: r.id, name: r.name, category: r.category, image_url: "/delayed-legacy.svg" } : r);
    await mock(page, items as typeof records);
    await page.route("**/delayed-legacy.svg", async route => {
        await gate;
        await route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="600"/>' });
    });
    await page.goto("/museum", { waitUntil: "domcontentloaded" });
    await expect(page.locator("[data-atlas-museum-card]")).toHaveCount(3);
    await card(page, "carta_vieja-2").dispatchEvent("click");
    await centered(page, "carta_vieja-2");
    release();
    await expect.poll(() => card(page, "carta_vieja-0").evaluate(node => { const image = node.querySelector("img")!; return image.clientWidth / image.clientHeight; })).toBeGreaterThan(3.9);
    await centered(page, "carta_vieja-2");
});

test("orientation changes keep the centered artwork and horizontal cards clear of the selector", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mock(page);
    await page.goto("/museum");
    await page.getByRole("button", { name: "Cartas Nuevas", exact: true }).click();
    await card(page, "carta_nueva-1").dispatchEvent("click");
    await centered(page, "carta_nueva-1");
    await page.setViewportSize({ width: 844, height: 390 });
    await centered(page, "carta_nueva-1");
    const rect = await card(page, "carta_nueva-1").boundingBox();
    const selector = await page.locator("[data-atlas-museum-selector]").boundingBox();
    expect(rect!.x).toBeGreaterThan(selector!.x + selector!.width);
    expect(rect!.y).toBeGreaterThanOrEqual(16);
    expect(rect!.y + rect!.height).toBeLessThanOrEqual(374);
    await page.setViewportSize({ width: 390, height: 844 });
    await centered(page, "carta_nueva-1");
});

for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }]) {
    test(`native touch swipes in both directions at ${viewport.width}x${viewport.height}`, async ({ browser, browserName }) => {
        test.skip(browserName !== "chromium", "Native CDP touch input is Chromium-only; WebKit wheel and viewer gestures are covered separately");
        const context = await browser.newContext({ viewport, isMobile: true, hasTouch: true });
        try {
            const page = await context.newPage();
            await mock(page);
            const touch = await context.newCDPSession(page);
            await page.goto("/museum");
            const stage = page.locator("[data-atlas-museum-stage]");
            const swipe = async (forward: boolean) => {
                const box = await stage.boundingBox();
                if (!box) throw new Error("No stage for swipe");
                const start = forward ? 0.8 : 0.2, end = forward ? 0.2 : 0.8;
                const point = (position: number) => ({ x: box.x + box.width * position, y: box.y + box.height / 2, id: 1 });
                await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point(start)] });
                for (let step = 1; step <= 10; step++) {
                    await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [point(start + (end - start) * step / 10)] });
                }
                await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
                await stage.evaluate(node => new Promise<void>(resolve => {
                    let previous = node.scrollLeft, stable = 0, frames = 0;
                    const tick = () => {
                        stable = Math.abs(node.scrollLeft - previous) < 0.5 ? stable + 1 : 0;
                        previous = node.scrollLeft;
                        if (stable >= 12 || frames++ > 240) resolve();
                        else requestAnimationFrame(tick);
                    };
                    requestAnimationFrame(tick);
                }));
            };
            for (let i = 0; i < labels.length; i++) {
                await page.getByRole("button", { name: labels[i], exact: true }).click();
                await centered(page, `${categories[i]}-0`);
                const before = await stage.evaluate(node => node.scrollLeft);
                await swipe(true);
                const after = await stage.evaluate(node => node.scrollLeft);
                expect(after).toBeGreaterThan(before + 30);
                await swipe(false);
                expect(await stage.evaluate(node => node.scrollLeft)).toBeLessThan(after - 30);
                await expect(page.locator("[data-atlas-museum-artwork-overlay]")).toHaveCount(0);
            }
        } finally {
            await context.close();
        }
    });
}

test("published archive images load completely in all four collection frames", async ({ page }) => {
    // This now loads the complete archive, rather than the original 12-image pilot.
    test.setTimeout(60_000);
    const published = JSON.parse(readFileSync(new URL("../../data/museum.json", import.meta.url), "utf8"));
    await page.setViewportSize({ width: 390, height: 844 });
    await mock(page, published);
    await page.goto("/museum");
    for (let i = 0; i < labels.length; i++) {
        await page.getByRole("button", { name: labels[i], exact: true }).click();
        const images = page.locator("[data-atlas-museum-card] img");
        await expect.poll(() => images.evaluateAll(nodes => nodes.length > 0 && nodes.every(node => node.complete && node.naturalWidth > 0)), {
            timeout: 15_000,
            message: `Published ${labels[i]} images must all finish loading without errors`,
        }).toBe(true);
        await expect.poll(() => images.evaluateAll(nodes => nodes.filter(image => {
            const css = getComputedStyle(image);
            const scale = Math.min(image.clientWidth / image.naturalWidth, image.clientHeight / image.naturalHeight);
            const bands = Math.max(image.clientWidth - image.naturalWidth * scale, image.clientHeight - image.naturalHeight * scale);
            return css.objectFit !== "contain" || image.clientWidth > image.parentElement!.clientWidth
                || image.clientHeight > image.parentElement!.clientHeight || bands > 1.5;
        }).length)).toBe(0);
    }
});

test("natural image dimensions supersede inaccurate metadata in every collection", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mock(page, records.map(item => ({ ...item, manifest_metadata: { width: "1000", height: "1000" } })));
    await page.goto("/museum");
    for (const label of labels) {
        await page.getByRole("button", { name: label, exact: true }).click();
        const images = page.locator("[data-atlas-museum-card] img");
        await expect.poll(() => images.evaluateAll(nodes => nodes.length === 3 && nodes.every(image => {
            if (!image.complete || image.naturalWidth === 0) return false;
            const scale = Math.min(image.clientWidth / image.naturalWidth, image.clientHeight / image.naturalHeight);
            return Math.max(image.clientWidth - image.naturalWidth * scale, image.clientHeight - image.naturalHeight * scale) <= 1.5;
        }))).toBe(true);
    }
});

test.describe("bounded animation with mounted collections", () => {
    test.use({ hasTouch: true });

    for (const count of [8, 135]) {
        for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }]) {
            test(`${count} slots keep centering, rapid navigation and cleanup at ${viewport.width}x${viewport.height}`, async ({ page, browserName }) => {
                test.setTimeout(60_000);
                await page.setViewportSize(viewport);
                await page.addInitScript(() => {
                    const audit = (window as any).__animationAudit = { pending: new Set<number>(), callbacks: 0, cardRenders: 0 };
                    const request = window.requestAnimationFrame.bind(window);
                    const cancel = window.cancelAnimationFrame.bind(window);
                    window.requestAnimationFrame = callback => {
                        const id = request(time => { audit.pending.delete(id); audit.callbacks++; callback(time); });
                        audit.pending.add(id);
                        return id;
                    };
                    window.cancelAnimationFrame = id => { audit.pending.delete(id); cancel(id); };
                    let renderer = 0;
                    (window as any).__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
                        supportsFiber: true, renderers: new Map(),
                        inject(value: unknown) { this.renderers.set(++renderer, value); return renderer; },
                        onCommitFiberRoot(_: unknown, root: any) {
                            const visit = (fiber: any) => {
                                if (!fiber) return;
                                if ((fiber.flags & 1) && fiber.type?.name === "BeerCoverV2") audit.cardRenders++;
                                visit(fiber.child); visit(fiber.sibling);
                            };
                            visit(root.current);
                        },
                        onCommitFiberUnmount() {}, onPostCommitFiberRoot() {},
                    };
                });
                const items = Array.from({ length: count }, (_, i) => ({
                    ...records[i % 3], id: `large-${i}`, name: `Artwork ${i}`,
                }));
                await mock(page, items);
                await page.goto("/museum");
                await page.getByRole("button", { name: "Tablas", exact: true }).click();
                const slots = page.locator("[data-atlas-museum-card]");
                const stage = page.locator("[data-atlas-museum-stage]");
                await expect(slots).toHaveCount(count);
                await expect.poll(() => slots.locator("img").evaluateAll(images => images.every(image => (image as HTMLImageElement).complete))).toBe(true);
                const geometry = () => slots.evaluateAll(nodes => nodes.map(node => {
                    const slot = node as HTMLElement;
                    return [slot.dataset.atlasMuseumCardId, slot.offsetLeft, slot.offsetWidth, slot.offsetHeight];
                }));
                await centered(page, "large-0");
                const originalGeometry = await geometry();
                const activeLoops = () => page.evaluate(() => (window as any).__animationAudit.pending.size);
                await expect.poll(activeLoops).toBeGreaterThan(0);
                await expect.poll(activeLoops).toBeLessThanOrEqual(Math.min(count, 16));

                const activate = async (index: number) => {
                    const id = `large-${index}`;
                    await card(page, id).dispatchEvent("click");
                    await centered(page, id);
                    await expect.poll(() => card(page, id).locator("[data-atlas-museum-visual]").evaluate(node => {
                        const angle = (node as HTMLElement).style.transform.match(/rotateY\(([-\d.]+)deg\)/);
                        return angle ? Math.abs(Number(angle[1])) : Infinity;
                    })).toBeLessThanOrEqual(2);
                    await expect.poll(activeLoops).toBeLessThanOrEqual(Math.min(count, 16));
                };
                for (const index of [Math.floor(count / 2), count - 1, 0]) await activate(index);

                // Large instantaneous jumps exercise cards whose transforms have been frozen.
                for (const index of [count - 1, 0, Math.floor(count / 2), count - 1, 0]) {
                    await card(page, `large-${index}`).evaluate(node => {
                        const slot = node as HTMLElement;
                        const stage = slot.closest("[data-atlas-museum-stage]")!;
                        stage.scrollTo({ left: slot.offsetLeft + slot.offsetWidth / 2 - stage.clientWidth / 2, behavior: "instant" });
                    });
                    await centered(page, `large-${index}`);
                    await expect.poll(() => card(page, `large-${index}`).locator("[data-atlas-museum-visual]").evaluate(node => {
                        const angle = (node as HTMLElement).style.transform.match(/rotateY\(([-\d.]+)deg\)/);
                        return angle ? Math.abs(Number(angle[1])) : Infinity;
                    })).toBeLessThanOrEqual(2);
                }

                const rendersBefore = await page.evaluate(() => (window as any).__animationAudit.cardRenders);
                await page.mouse.move(viewport.width / 2, viewport.height / 2);
                await page.mouse.wheel(700, 0);
                await expect.poll(() => stage.evaluate(node => node.scrollLeft)).toBeGreaterThan(100);
                await page.mouse.wheel(-2000, 0);
                await centered(page, "large-0");
                expect(await page.evaluate(() => (window as any).__animationAudit.cardRenders)).toBe(rendersBefore);

                if (browserName === "chromium") {
                    const touch = await page.context().newCDPSession(page);
                    const swipe = async (forward: boolean) => {
                        const start = forward ? 0.8 : 0.2, end = forward ? 0.2 : 0.8;
                        const point = (x: number) => ({ x: viewport.width * x, y: viewport.height / 2, id: 1 });
                        await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point(start)] });
                        for (let step = 1; step <= 10; step++) {
                            await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [point(start + (end - start) * step / 10)] });
                        }
                        await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
                    };
                    const before = await stage.evaluate(node => node.scrollLeft);
                    await swipe(true);
                    await expect.poll(() => stage.evaluate(node => node.scrollLeft)).toBeGreaterThan(before + 30);
                    // Let native momentum and snapping settle before reversing direction.
                    await page.waitForTimeout(600);
                    const after = await stage.evaluate(node => node.scrollLeft);
                    await swipe(false);
                    await expect.poll(() => stage.evaluate(node => node.scrollLeft)).toBeLessThan(after - 30);
                }
                expect(await geometry()).toEqual(originalGeometry);
                for (let repeat = 0; repeat < 2; repeat++) {
                    await page.getByRole("button", { name: "Etiquetas", exact: true }).click();
                    await expect(slots).toHaveCount(0);
                    await expect.poll(activeLoops).toBe(0);
                    await page.getByRole("button", { name: "Tablas", exact: true }).click();
                    await expect(slots).toHaveCount(count);
                    await centered(page, "large-0");
                    await expect.poll(activeLoops).toBeGreaterThan(0);
                    await expect.poll(activeLoops).toBeLessThanOrEqual(Math.min(count, 16));
                }
            });
        }
    }
});
