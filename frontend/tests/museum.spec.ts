import { test, expect } from "@playwright/test";

test("ATLAS Museum core behavior", async ({ page }) => {
    test.setTimeout(90_000);

    const criticalErrors = [];
    const stageSelector = "[data-atlas-museum-stage]";
    const trackSelector = "[data-atlas-museum-track]";
    const overlay = page.locator('div[style*="z-index: 9999;"]');

    page.on("pageerror", error => {
        criticalErrors.push(`[pageerror] ${error.message}`);
    });

    page.on("console", message => {
        if (message.type() === "error") {
            criticalErrors.push(`[console] ${message.text()}`);
        }
    });

    await page.goto("http://bs-local.com:3000/museum");

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
    await expect(selector.getByRole("button")).toHaveCount(2);
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
