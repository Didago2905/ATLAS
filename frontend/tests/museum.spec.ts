import { test, expect } from "@playwright/test";

const museumUrl = "http://bs-local.com:3000/museum";
const image = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='300'%3E%3Crect width='100%25' height='100%25' fill='%23222'/%3E%3C/svg%3E";
const museumItems = [
    { id: "museum-1", name: "Museum One", type: "fichas/antiguas", image_url: image },
    { id: "museum-2", name: "Museum Two", type: "fichas/antiguas", image_url: image },
    { id: "museum-3", name: "Museum Three", type: "fichas/antiguas", image_url: image },
];
const tapItems = [
    { id: 201, name: "Tap One", brewery: "Tiburon", style: "IPA", color: "#222222", abv: 5, image_url: image, is_available: true, is_featured: false, tap_position: 1 },
];

async function routeMuseumData(page) {
    await page.route("**/api/public/museum", route =>
        route.fulfill({ json: museumItems })
    );
    await page.route("**/api/public/tap", route =>
        route.fulfill({ json: tapItems })
    );
}

async function openMuseum(page) {
    await routeMuseumData(page);
    await page.goto(museumUrl);
    await expect(page.locator("[data-atlas-museum-stage]")).toBeVisible();
    await expect(page.locator("[data-atlas-museum-card]")).toHaveCount(3);
}

async function openFirstArtwork(page) {
    await page.locator('[data-atlas-museum-card-id="museum-1"]').click();
    await expect(page.locator("[data-atlas-museum-artwork-overlay]")).toBeVisible();
}

async function dragArtwork(page, deltaY) {
    const overlay = page.locator("[data-atlas-museum-artwork-overlay]");
    const box = await overlay.boundingBox();

    if (!box) throw new Error("Artwork overlay has no bounding box");

    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x, y + deltaY, { steps: 5 });
    await page.mouse.up();
}

test("ATLAS Museum core behavior", async ({ page }) => {
    test.setTimeout(90_000);

    const criticalErrors = [];
    const stageSelector = "[data-atlas-museum-stage]";
    const trackSelector = "[data-atlas-museum-track]";
    const overlay = page.locator("[data-atlas-museum-artwork-overlay]");

    page.on("pageerror", error => {
        criticalErrors.push(`[pageerror] ${error.message}`);
    });

    page.on("console", message => {
        if (message.type() === "error") {
            criticalErrors.push(`[console] ${message.text()}`);
        }
    });

    await routeMuseumData(page);
    await page.goto(museumUrl);

    const stage = page.locator(stageSelector);
    const track = page.locator(trackSelector);
    const selector = page.locator("[data-atlas-museum-selector]");

    const getSlot = async (cardIndex) => {
        const children = track.locator(":scope > div");
        let discoveredCards = 0;

        for (let childIndex = 0; childIndex < await children.count(); childIndex += 1) {
            const child = children.nth(childIndex);

            if (await child.locator("img").count() === 0) continue;
            if (discoveredCards === cardIndex) return child;

            discoveredCards += 1;
        }

        throw new Error(`BeerCover layout slot ${cardIndex} was not found`);
    };

    const readTrackSnapshot = async () => track.evaluate(trackElement => {
        const stageElement = trackElement.parentElement;

        if (!stageElement) {
            throw new Error("Museum stage is unavailable for behavior testing");
        }

        const stageRect = stageElement.getBoundingClientRect();
        const stageCenter =
            stageElement.scrollLeft + stageElement.offsetWidth / 2;
        const cards = Array.from(trackElement.children).filter(
            child => child.querySelector("img")
        ).map((card, index) => {
            const rect = card.getBoundingClientRect();
            const layoutCenter = card.offsetLeft + card.offsetWidth / 2;

            return {
                index,
                layoutDistance: Math.abs(layoutCenter - stageCenter),
                clickSafe: rect.left >= stageRect.left + 8 &&
                    rect.right <= stageRect.right - 8,
            };
        });
        const nearestCard = cards.reduce((nearest, card) =>
            !nearest || card.layoutDistance < nearest.layoutDistance
                ? card
                : nearest
        , null);

        return {
            cardCount: cards.length,
            scrollLeft: stageElement.scrollLeft,
            cards,
            nearestCardIndex: nearestCard?.index ?? -1,
        };
    });

    const findClickSafeOffCenterCard = snapshot => snapshot.cards.find(card =>
        card.clickSafe && card.layoutDistance > 10
    );

    await expect(stage).toBeVisible();
    await expect(track).toBeVisible();
    await expect(selector).toBeVisible();
    await expect(selector.getByRole("button")).toHaveCount(3);
    await expect.poll(async () => (await readTrackSnapshot()).cardCount)
        .toBeGreaterThan(0);

    const fichas = await readTrackSnapshot();
    await expect(await getSlot(0)).toBeVisible();

    const anchorIndex = fichas.nearestCardIndex < fichas.cardCount - 1
        ? fichas.nearestCardIndex + 1
        : fichas.nearestCardIndex - 1;
    const anchor = fichas.cards[anchorIndex];

    expect(anchor, "Museum core behavior requires at least two cards")
        .toBeTruthy();

    const direction = anchor.index > fichas.nearestCardIndex ? 1 : -1;

    // Synthetic scroll-mechanics coverage; this is not native-touch coverage.
    await stage.hover();
    await page.mouse.wheel(direction * 200, 0);
    await expect.poll(
        async () => Math.abs(
            (await readTrackSnapshot()).scrollLeft - fichas.scrollLeft
        ),
        { timeout: 5_000 }
    ).toBeGreaterThanOrEqual(40);

    const afterScroll = await readTrackSnapshot();
    const target = findClickSafeOffCenterCard(afterScroll);

    expect(target, "Expected a click-safe off-center BeerCover layout slot")
        .toBeTruthy();

    const targetSlot = await getSlot(target.index);

    await targetSlot.click();
    await expect(overlay).toHaveCount(0);
    await expect.poll(
        async () => (await readTrackSnapshot()).cards[target.index]
            ?.layoutDistance ?? Infinity,
        { timeout: 5_000 }
    ).toBeLessThanOrEqual(15);

    await targetSlot.click();
    await expect(overlay).toBeVisible();

    await overlay.click({ position: { x: 5, y: 5 } });
    await expect(overlay).toHaveCount(0);

    await selector.getByRole("button").nth(1).click();
    await expect.poll(async () => (await readTrackSnapshot()).cardCount, {
        timeout: 5_000,
    }).not.toBe(fichas.cardCount);

    const tap = await readTrackSnapshot();

    expect(tap.cardCount).toBeGreaterThan(0);
    await expect(await getSlot(0)).toBeVisible();
    expect(criticalErrors).toEqual([]);
});

test("Museum background defaults to black without a stored preference", async ({ page }) => {
    await openMuseum(page);

    const stage = page.locator("[data-atlas-museum-stage]");
    await expect.poll(() => stage.evaluate(element =>
        getComputedStyle(element).backgroundColor
    )).toBe("rgb(0, 0, 0)");
    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("atlas_museum_background")
    )).toBe("black");
});

test("Museum background rejects an invalid stored preference", async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("atlas_museum_background", "invalid-background");
    });
    await openMuseum(page);

    const stage = page.locator("[data-atlas-museum-stage]");
    await expect.poll(() => stage.evaluate(element =>
        getComputedStyle(element).backgroundColor
    )).toBe("rgb(0, 0, 0)");
    await expect.poll(() => page.evaluate(() =>
        localStorage.getItem("atlas_museum_background")
    )).toBe("black");
});

test("Museum background selector opens, closes, and applies all canonical backgrounds", async ({ page }) => {
    await openMuseum(page);

    const stage = page.locator("[data-atlas-museum-stage]");
    const trigger = page.locator("[data-atlas-museum-background-trigger]");
    const popover = page.locator("[data-atlas-museum-background-popover]");

    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await trigger.click();
    await expect(popover).toBeVisible();
    await expect(popover.getByRole("menuitemradio")).toHaveCount(4);
    await trigger.click();
    await expect(popover).toHaveCount(0);

    const expectedCenterColors = {
        "gallery-light": "rgb(240, 237, 230)",
        petrol: "rgb(52, 70, 77)",
        burgundy: "rgb(89, 48, 57)",
    };

    for (const id of ["black", "gallery-light", "petrol", "burgundy"]) {
        await trigger.click();
        const option = page.locator(`[data-atlas-museum-background-option="${id}"]`);
        await option.click();
        await expect(popover).toHaveCount(0);
        await expect.poll(() => page.evaluate(() =>
            localStorage.getItem("atlas_museum_background")
        )).toBe(id);

        const background = await stage.evaluate(element => ({
            color: getComputedStyle(element).backgroundColor,
            image: getComputedStyle(element).backgroundImage,
        }));

        if (id === "black") {
            expect(background.color).toBe("rgb(0, 0, 0)");
        } else {
            expect(background.image).toContain("radial-gradient");
            expect(background.image).toContain(expectedCenterColors[id]);
        }
    }
});

test("Museum background preference survives reload", async ({ page }) => {
    await openMuseum(page);

    await page.locator("[data-atlas-museum-background-trigger]").click();
    await page.locator('[data-atlas-museum-background-option="burgundy"]').click();
    await page.reload();

    await expect(page.locator("[data-atlas-museum-stage]")).toBeVisible();
    await expect.poll(() => page.locator("[data-atlas-museum-stage]").evaluate(element =>
        getComputedStyle(element).backgroundImage
    )).toContain("radial-gradient");
    await page.locator("[data-atlas-museum-background-trigger]").click();
    await expect(page.locator('[data-atlas-museum-background-option="burgundy"]'))
        .toHaveAttribute("aria-checked", "true");
});

test("Museum normalizes legacy background aliases to canonical IDs", async ({ page }) => {
    await openMuseum(page);

    const aliases = [
        ["bone", "gallery-light"],
        ["dark-gradient", "petrol"],
        ["sand-gradient", "burgundy"],
    ];

    for (const [legacyId, canonicalId] of aliases) {
        await page.evaluate(id => {
            localStorage.setItem("atlas_museum_background", id);
        }, legacyId);
        await page.reload();
        await expect(page.locator("[data-atlas-museum-stage]")).toBeVisible();
        await expect.poll(() => page.evaluate(() =>
            localStorage.getItem("atlas_museum_background")
        )).toBe(canonicalId);
        await page.locator("[data-atlas-museum-background-trigger]").click();
        await expect(page.locator(
            `[data-atlas-museum-background-option="${canonicalId}"]`
        )).toHaveAttribute("aria-checked", "true");
    }
});

test("full artwork preserves the selected Museum background", async ({ page }) => {
    await openMuseum(page);

    await page.locator("[data-atlas-museum-background-trigger]").click();
    await page.locator('[data-atlas-museum-background-option="petrol"]').click();
    const stageBackground = await page.locator("[data-atlas-museum-stage]")
        .evaluate(element => getComputedStyle(element).backgroundImage);

    await openFirstArtwork(page);

    await expect.poll(() => page.locator("[data-atlas-museum-artwork-background]")
        .evaluate(element => getComputedStyle(element).backgroundImage))
        .toBe(stageBackground);
});

test("artwork dismisses with equivalent downward and upward drags", async ({ page }) => {
    await openMuseum(page);

    await openFirstArtwork(page);
    await dragArtwork(page, 200);
    await expect(page.locator("[data-atlas-museum-artwork-overlay]")).toHaveCount(0);

    await openFirstArtwork(page);
    await dragArtwork(page, -200);
    await expect(page.locator("[data-atlas-museum-artwork-overlay]")).toHaveCount(0);
});

test("short artwork drags restore in both vertical directions", async ({ page }) => {
    await openMuseum(page);
    await openFirstArtwork(page);

    for (const deltaY of [40, -40]) {
        await dragArtwork(page, deltaY);
        const visual = page.locator("[data-atlas-museum-artwork-visual]");
        await expect(visual).toBeVisible();
        await expect.poll(() => visual.evaluate(element => {
            const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform);
            return Math.max(Math.abs(matrix.m41), Math.abs(matrix.m42));
        })).toBeLessThanOrEqual(1);
    }
});

test("Museum navigation hides the selector and closes its popover", async ({ page }) => {
    await openMuseum(page);

    const selector = page.locator("[data-atlas-museum-selector]");
    const trigger = page.locator("[data-atlas-museum-background-trigger]");
    const popover = page.locator("[data-atlas-museum-background-popover]");
    await trigger.click();
    await expect(popover).toBeVisible();

    const hiddenState = await page.evaluate(() => new Promise(resolve => {
        const event = new Event("touchmove", { bubbles: true });
        window.dispatchEvent(event);
        requestAnimationFrame(() => {
            const selector = document.querySelector("[data-atlas-museum-selector]");
            resolve({
                opacity: selector?.style.opacity,
                pointerEvents: selector?.style.pointerEvents,
            });
        });
    }));

    await expect(popover).toHaveCount(0);
    expect(hiddenState).toEqual({ opacity: "0", pointerEvents: "none" });
    await expect.poll(() => selector.evaluate(element =>
        getComputedStyle(element).opacity
    ), { timeout: 2_000 }).toBe("1");
});

test("outside interaction closes the popover without blocking BeerCoverV2", async ({ page }) => {
    await openMuseum(page);

    const popover = page.locator("[data-atlas-museum-background-popover]");
    await page.locator("[data-atlas-museum-background-trigger]").click();
    await expect(popover).toBeVisible();

    await page.locator('[data-atlas-museum-card-id="museum-1"]').click();

    await expect(popover).toHaveCount(0);
    await expect(page.locator("[data-atlas-museum-artwork-overlay]")).toBeVisible();
});

test("landscape scales only the visual layer while portrait and layout slots stay stable", async ({ page }) => {
    const readCards = () => page.locator("[data-atlas-museum-card]").evaluateAll(cards =>
        cards.map(card => {
            const visual = card.querySelector("[data-atlas-museum-visual]");
            if (!visual) throw new Error("Museum visual layer is unavailable");
            const matrix = new DOMMatrixReadOnly(getComputedStyle(visual).transform);
            return {
                slotWidth: (card as HTMLElement).offsetWidth,
                slotHeight: (card as HTMLElement).offsetHeight,
                baseScale: Number(visual.getAttribute("data-atlas-museum-visual-scale")),
                renderedScale: Math.hypot(matrix.m11, matrix.m12, matrix.m13),
            };
        })
    );

    await page.setViewportSize({ width: 700, height: 900 });
    await openMuseum(page);
    await expect.poll(async () => (await readCards())[0].baseScale).toBe(1);
    const portrait = await readCards();

    await page.setViewportSize({ width: 900, height: 700 });
    await expect.poll(async () => (await readCards())[0].baseScale).toBe(0.95);
    const landscape = await readCards();

    expect(landscape.map(card => [card.slotWidth, card.slotHeight]))
        .toEqual(portrait.map(card => [card.slotWidth, card.slotHeight]));
    expect(portrait.every(card => card.baseScale === 1)).toBe(true);
    expect(landscape.every(card => card.baseScale === 0.95)).toBe(true);

    const portraitScales = portrait.map(card => card.renderedScale);
    const landscapeScales = landscape.map(card => card.renderedScale);
    expect(Math.max(...portraitScales)).toBeGreaterThan(Math.min(...portraitScales));
    expect(Math.max(...landscapeScales)).toBeGreaterThan(Math.min(...landscapeScales));
    expect(Math.max(...landscapeScales) / Math.max(...portraitScales)).toBeCloseTo(0.95, 1);
});
